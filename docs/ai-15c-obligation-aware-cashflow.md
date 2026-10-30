# AI-15C: obligation-aware cashflow and reservation

## Problem and accounting semantics

AI-15B already reduced aggregate scheduled reserves, but used a separate SQL calculation. Upcoming expense signals and snapshot item details continued to report full principal, including fully allocated schedules still marked scheduled. The result could contradict the reserve and prompt a user to pay an already settled obligation.

`finance/obligations.py` provides immutable Decimal amounts:

    remaining_amount = max(original_amount - active_confirmed_allocations, 0)
    reserved_amount = remaining_amount if status == scheduled else 0

The original ScheduledCashflowItem.amount is never changed. A manually paid or cancelled item reserves zero even without allocation history; its mathematical remaining principal remains auditable. Candidate suggestions have no accounting effect. Revoked rows are ignored and revoking a settled allocation restores the schedule through the existing AI-15B transition.

> Confirmed allocation affects the remaining scheduled obligation; it does not create or modify a transaction.

## Repository inspection and integration

Inspected origin/main (4707efb), AI-09 forecasting, AI-11 coach/planner scheduling, AI-15A account reconciliation, and AI-15B repository, service, CRUD, models, tests, and documentation before editing. No AGENTS.md files were found in this repository. Existing untracked CSVs and the frontend redesign directory are excluded from this milestone.

The integration point is intelligence.facts.scheduled_totals, shared by coach_cashflow, purchase affordability, intelligence cashflow, and goal capacity. It now consumes the same obligation values as snapshot details and upcoming expense signals. Batch reads reuse the owner-scoped active allocation repository used by allocated_total(); single-item reads reuse allocated_total(). There is no independent allocation SQL formula. Both income and expense plans use remaining principal. Fully allocated schedules produce no future scheduled event, even if status is still scheduled. Signal limits apply after settled rows are removed.

AI-09's historical-only /forecast/cashflow baseline and the historical savings planner remain historical estimates. They do not convert scheduled items and retain their existing contracts. AI-11's /finance cashflow scenario is the existing reservation-aware forecast: it reserves max(historical expense estimate, remaining scheduled expenses), preserving the overlap assumption. Remaining scheduled income is shown separately as uncertain income and is never added to available cash or projected balances. No new forecast convention or guaranteed-income assumption is introduced.

## Dates, actuals, and concurrency

All existing inclusive due-date windows are preserved. Coach scenarios begin as of the supplied date, prorate the current month, and exclude overdue schedules. The intelligence cashflow current-month summary retains its existing month-start window. Purchase horizons and upcoming signals retain their own existing inclusive windows. No overdue roll-forward or recurring expansion is added.

Actual transactions remain authoritative for observed totals and historical averages. Allocation never subtracts from those totals, modifies imported amounts, or produces synthetic transactions. Future scheduled reserves use remaining principal only. The existing max-of-historical-and-scheduled expense policy avoids adding the same estimated bill twice, but does not claim to reconcile every historical estimate with a particular bill.

AI-15A balance derivation is unchanged: opening balance, transaction snapshots, signed principal and separately recorded fees retain their existing meaning. AI-15B confirmation, revocation, ownership constraints and PostgreSQL owner locking remain in force. Read-only calculation adds no locks or second write mechanism. Existing concurrent confirmation/idempotency/conflicting-obligation tests remain applicable.

## API and frontend

No new endpoint or migration. Intelligence PlannedObservation adds optional original_amount, allocated_amount and remaining_amount fields. Its existing amount now describes the outstanding upcoming plan; scheduled CRUD amount continues to mean original principal. Snapshot serialization and signal evidence expose the deterministic breakdown. Totals retain their existing shapes. Generated TypeScript contracts are updated.

The Cashflow UI already shows original principal, allocated principal, remaining principal, and allocation controls with English/Bengali translations. No rendering, layout, or translation changes are needed. Generated types are the only frontend source change.

## Tests and validation

Focused tests cover unpaid, partial, exact settlement while still scheduled, multiple allocations, Decimal cents, both directions, candidate-only behavior, revocation, manual paid and cancelled records, user isolation, inclusive boundaries and overdue exclusion, unchanged actual transaction totals, coach reservation balances, purchase affordability, serialized API breakdown, signal evidence, and defensive clamping. The full backend suite also exercises existing PostgreSQL allocation concurrency guarantees.

Validation completed:

- Focused AI-15C suite: 11 passed.
- Full backend (`python -m pytest backend -q --tb=short`): 429 passed, 1 existing opt-in smoke test skipped; 7 existing Alembic configuration deprecation warnings.
- `python -m compileall backend`: passed.
- Generated frontend contracts check: passed.
- Frontend typecheck, lint and production build: passed.
- Chrome browser suite: 21 passed, 5 existing duplicate mobile viewport cases skipped; covers English/Bengali, mobile, keyboard accessibility, and obligation confirmation/revocation.
- `git diff --check`: passed.


## Known limitations

Batch calculation reads the user's active allocations once per fact query; large histories may warrant an indexed aggregate later. Separate API calls are live reads and can observe a newer committed state after confirmation or revocation. Historical forecast averages can still contain past bill payments; the existing maximum reservation policy is an estimate rather than per-bill forecast reconciliation. Scheduled income remains uncertain. No FX conversion, automatic settlement, transaction splitting, fees allocation, recurring-instance expansion, or LLM calls are added.
