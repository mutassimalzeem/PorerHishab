# AI-15D: deterministic financial cash position and runway

## Purpose and integration

Built from main at f21341d after inspecting AI-15A account reconciliation and APIs, AI-15B allocations/locking/lifecycle, AI-15C obligations/facts/tests/documentation, historical forecasting, goal capacity, purchase decisions, intelligence signals/snapshots, and frontend contracts. No repository AGENTS.md files were found. Local transaction CSVs and the untracked frontend redesign are preserved.

`services/finance/runway.py` is the authoritative read-only engine. It uses AI-15A reconciliation, AI-15C scheduled_obligation_values, the existing complete-month history/coverage gate and money rounding, and existing calendar helpers. It introduces no SQL allocation formula, write locks, migrations, provider calls, transaction mutations or synthetic transactions.

Allocations are reconciliation metadata, not transactions.

## Accounting and balance-source selection

Only the authenticated user's BDT accounts are included. Foreign currencies are excluded without conversion. Every included account must have an established balance: an unknown account, disagreement between report and derivation, or no BDT accounts makes aggregate starting_balance null. A partial account sum is never represented as total cash.

Per account, choose the AI-15A reconciled/derived balance when available, otherwise its reported balance. Expose reported and derived aggregates separately only when every included account has that respective value. The source is reconciled, derived, reported, mixed or unknown. Mixed means different usable source types across accounts. Negative and exact-zero cash are valid, distinct from unknown. Derived balances are not independently reconstructed by the runway engine.

AI-15A now accepts an optional as_of date. Its default behavior is unchanged. The cutoff excludes later transactions, later opening balances and reports whose timestamp falls after the date in Asia/Dhaka. This is needed to avoid a future-dated actual changing an earlier starting position. Undated reports remain low-confidence reports, never verified bank balances. Stale reports and incomplete imports are explicit limitations; this milestone does not invent a freshness cutoff or bank integration.

## Forecast horizon and obligations

Use today_dhaka() unless as_of is supplied. Horizon is 1..366 days, with end = as_of + horizon_days; both endpoints are included, matching existing future-scenario and purchase conventions. Thus a horizon of 30 includes 31 calendar dates. Overdue obligations are excluded rather than silently moved forward.

Remaining principal, active/revoked semantics and terminal paid/cancelled behavior come exclusively from AI-15C. Original principal remains auditable on the schedule and reconciliation APIs. Candidates have no accounting effect. Multiple confirmed principal allocations reduce the reserve; revocation restores it. Fully allocated schedules contribute no future event even before an explicit paid transition.

Remaining scheduled income is exposed as known_future_income, meaning a known plan rather than certain receipts. Scheduled income remains uncertain and is never added to available cash or either scenario's projected balance.

## Two explicit scenarios and runway resolution

### Historical (default)

Requires an established starting balance and the existing three complete prior calendar months with usable recorded activity. Missing history produces null forecast and projection fields with insufficient_data status; known obligations and known_obligations_end_balance remain available separately when starting cash is known.

Reuse the historical baseline's average income and expense. Split the inclusive horizon into calendar-month segments and prorate each estimate by covered days / calendar days in that month, using Decimal and existing half-up cent rounding. Each segment reserves max(prorated historical expenses, remaining scheduled expense obligations). Do not add overlapping scheduled bills on top of their historical estimate. expected_expense_reserve exposes the resulting reserve separately from forecast_expense and scheduled_expense_reserve.

For each segment:

    conservative low = opening cash - expense reserve
    ending cash = conservative low + estimated historical income

Minima conservatively assume expenses precede income within the segment. This can flag an intra-month risk even if the ending balance recovers. These are monthly estimates, not daily observations. A shortfall returns first_shortfall_period; first_shortfall_date and runway_days are null because income/spending timing cannot support an exact depletion day. Even a one-day partial segment remains an estimate.

### Known obligations

Explicit mode=known_obligations selects a limited no-income, scheduled-expense-only scenario. It needs starting cash but does not require historical coverage. Subtract only remaining obligations in due-date/id order. The first negative balance has a deterministic first_shortfall_date and runway_days relative to as_of, including day zero for already-negative cash. These refer only to the dated-obligations scenario and are not a complete prediction of when real cash will run out. No finite runway is extrapolated beyond the horizon. Confidence is low because general spending/income is deliberately excluded.

## Status, confidence and uncertainty

- cash_shortfall: minimum projected cash is strictly negative.
- at_risk: minimum is nonnegative but at or below safety_threshold.
- positive: minimum stays strictly above safety_threshold throughout the selected scenario.
- insufficient_data: required balance/history cannot be established; projection fields remain null.

The configurable nonnegative safety threshold defaults to zero BDT. It is a caller-selected floor, not a personalized recommendation. No undisclosed low-balance percentage is used. Confidence is deterministic: high for reconciled account cash plus adequate history, medium for derived/snapshot sources with adequate history, low for reported/mixed weak sources or the limited scenario, unknown for insufficient data. Confidence cannot establish bank verification or complete transaction coverage.

## Actual versus scheduled: double-counting rules

Starting cash already reflects actual transactions through as_of using AI-15A principal/fee semantics. Do not subtract those actual transactions again when stepping forward. Allocations affect future remaining obligations only. For opening cash 30,000, rent 15,000 and a linked actual payment -6,000, starting cash is 24,000 and remaining reserve is 9,000; known-obligations ending cash is 15,000. A full 15,000 payment leaves starting cash 15,000 and future reserve zero. Revoking an allocation changes the reserve, not the actual transaction or starting balance.

As-of is a date-window selection, not versioned accounting replay. Schedule statuses and active allocations are current persisted state; the engine does not reconstruct historical allocation/report versions. Separate requests may observe later committed changes. Existing PostgreSQL confirmation/revocation ownership constraints and owner locks remain unchanged.

## API and response examples

Authenticated GET /finance/runway accepts:

- horizon_days (integer, default 30, range 1..366)
- as_of (optional ISO date, otherwise Bangladesh today)
- safety_threshold (nonnegative Decimal, up to two decimal places, default 0.00)
- mode (historical or known_obligations, default historical)

Money serializes as Decimal strings and unknowns as JSON null. No internal account or allocation ORM structures are exposed. Example selected response fields for the partial rent example, requested with mode=known_obligations:

```json
{
  "starting_balance": "24000.00",
  "balance_source": "derived",
  "known_future_income": "0.00",
  "scheduled_expense_reserve": "9000.00",
  "forecast_income": "0.00",
  "forecast_expense": "0.00",
  "expected_expense_reserve": "9000.00",
  "known_obligations_end_balance": "15000.00",
  "projected_end_balance": "15000.00",
  "minimum_projected_balance": "15000.00",
  "runway_status": "positive",
  "runway_days": null,
  "first_shortfall_date": null,
  "confidence": "low"
}
```

With no established starting cash, starting_balance, projected_end_balance and minimum_projected_balance are null; runway_status is insufficient_data and confidence unknown. A known reserve may still be present. Each response also supplies period, mode, safety_threshold, checkpoints, assumptions and limitations. Historical responses provide first_shortfall_period where supported.

## Consumer integration

Purchase coaching consumes the engine result. Its caller-confirmed starting cash is capped by established account cash when available; it cannot increase known cash. The decision is downgraded if the purchase breaches available cash after known obligations, the historical low-watermark, or the selected safety buffer. Existing caller-confirmed checks remain available where account/history coverage is absent, with explicit limitations and the underlying runway attached to the response. A caller report cannot validate conflicting account records. There is no second runway calculation in coach_purchase.

Goal capacity retains existing historical contribution/shared-goal arithmetic but is capped by nonnegative account cash remaining after the 30-day known-obligations horizon when that amount is established. Goal savings are not assumed to be additional account cash. The historical caller-balance cashflow scenario remains a separate explicitly supplied scenario; the new account-based summary does not silently replace its inputs.

Financial intelligence appends a cash_position signal using the authoritative result when projections exist. It carries period, estimate flag, minimum/reference/delta, source values, confidence, assumptions and limitations. Unknown projections generate no invented healthy/shortfall signal. Existing signal rules and identities remain intact.

The Cashflow page adds an on-request account-runway summary with original layout conventions, BDT formatting, bilingual English/Bengali labels, explicit unknown values, date window and limitations. It resets when schedule/allocation data changes and supports refresh. No charting dependency or UI redesign is introduced. Generated TypeScript contracts cover the new endpoint and coach/signal additions.

## Tests and validation

Focused SQLite tests cover source selection, reconciled/reported/derived/mixed/unknown and conflicting balances, partial aggregate rejection, snapshot/date cutoff behavior, ownership and FX isolation, unpaid/partial/multiple/exact/revoked/candidate/paid/cancelled obligations, income separation, unchanged actuals, precision, positive/threshold/negative cases, first dated shortfall, day-zero negatives, monthly-resolution uncertainty, proration across month boundaries, forecast overlap, historical coverage gating, purchase/goal restrictions, engine signals, API authentication/validation/serialization/nulls, and no float inputs for service money.

Existing AI-15A/B/C tests remain intact; PostgreSQL allocation concurrency tests are exercised by the full backend suite. The existing CI check now includes the new SQLite runway tests and AI-15A/C regression files. Frontend tests cover unknowns, refresh, error handling and Bengali output; desktop/mobile browser tests cover unknown-to-populated results, overflow and accessibility.

Validation completed:

- Focused AI-15D: 40 passed.
- Full backend: 469 passed, 1 existing opt-in smoke test skipped; 7 existing Alembic configuration deprecation warnings.
- Python compileall backend/app: passed.
- Generated frontend contracts check: passed.
- Frontend typecheck, lint, production build: passed.
- Frontend unit tests: 45 passed across 9 files, including 4 new runway summary tests.
- Chrome desktop/mobile browser suite: 23 passed, 5 existing duplicate viewport cases skipped; new runway scenarios include axe accessibility and overflow assertions.
- CI-selected SQLite tests with DATABASE_URL=sqlite:///:memory:: 122 passed.
- git diff --check: passed.

The first browser attempt exposed an authentication setup error in the new test: a full page reload discarded its in-memory login. The test now uses the existing authenticated navigation helper, and the subsequent complete suite passed. The account/report conflict regression was added during final review, followed by another complete backend run.


## Limitations and future extensions

Monthly forecasts cannot provide a precise real-world depletion date. The known-obligations scenario is incomplete by design. Historical averages can include prior bills; the existing maximum-overlap policy is a scenario assumption rather than per-bill forecast reconciliation. Reconciliation may rely on stale/undated reports, and linked/unlinked imports can be incomplete. Balance queries and allocation reads are live rather than a versioned multi-request snapshot. Internal transfers and credit liabilities have no new classification policy. FX conversion, recurring generation, automatic matching, bank integration, versioned as-of replay, richer dated forecasts and freshness policy remain separate milestones.
