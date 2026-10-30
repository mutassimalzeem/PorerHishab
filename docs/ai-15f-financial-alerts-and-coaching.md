# AI-15F: financial alerts and actionable coaching

## Purpose, inspection and architecture

Implemented from origin/main df3d4f9 on feature/ai-15f-financial-coaching. Inspected repository/working-tree state, README, AI-15B/C/D/E notes, AI-15A model/reconciliation/API/tests, allocation persistence/ownership/locking, obligation facts, runway/timeline, intelligence history/signals/categories/goals, spending decisions, auth, generated contracts, frontend Insights/Cashflow components, localization and test conventions. AI-15A has no separate milestone note; its implementation and reconciliation tests are the source. No AGENTS.md files were found. Unrelated CSVs and frontend redesign work are preserved.

The new finance/coaching.py service is a computed read-only presentation/rule layer over existing deterministic financial facts. It does not create a ledger, recalculate account balances, invent allocation state, generate another forecast, execute financial actions or call a provider. No database table or migration is needed: dismissal, delivery, notification state and feedback persistence are outside this MVP.

The existing /finance/intelligence endpoint describes observations/signals; legacy savings recommendations estimate optional spending cuts. A dedicated /finance/coaching endpoint exposes prioritized, deduplicated actions with evidence and expiry without breaking those contracts or turning a raw signal into an instruction to move money. Legacy views remain available. Deduplication applies within this consolidated feed; legacy signal lists are separate diagnostic views, not extra allocations of its savings amount.

## Reused sources and accounting

- AI-15A/15D supply starting cash, source, known-commitment cash, forecast low-watermark/end balance, scenario status and supported shortfall dates/windows.
- AI-15B/C supply active confirmed allocation amounts and remaining expenses through scheduled_obligation_values/scheduled_totals. Candidate suggestions have no effect; revocations restore reserves; paid/cancelled/fully allocated plans generate no unpaid recommendation.
- AI-15E shares those same obligation facts. Evidence references its stable obligation:<id> event identities without fetching a second raw timeline or summing history and projections.
- Intelligence monthly_history and category_spending_facts provide complete-month totals and coverage. Existing INCREASE_FACTOR, UNUSUAL_FACTOR and REDUCIBLE_CATEGORIES remain the policy sources for spending reviews.
- GoalAssessment supplies remaining targets, required monthly contribution, estimated capacity and affordability. Savings goal values remain user-reported; no contribution history is inferred.

Money remains Decimal. Current cash already reflects the actuals covered by AI-15A; allocations are reconciliation metadata, never additional transactions/outflows. The existing maximum of forecast spending and remaining scheduled expenses is retained by the runway engine. Scheduled income is displayed as uncertain evidence and never added to available cash or recommended savings amounts.

## Transfer classification and compatibility

Add an opt-in exclude_transfers keyword to shared totals, grouped category expenses, monthly history and category comparison facts. The default is false, preserving all AI-15A through AI-15E and legacy evaluation behavior. Only coaching opts in and supplies that filtered history to the existing runway service. Existing forecasting arithmetic is unchanged; the evidence inputs explicitly exclude classified transfers.

Exclusions use trimmed/case-normalized explicit category Transfer/Transfers or transaction_type transfer/internal_transfer/internal transfer. No merchant/description similarity, LLM guess or automatic matching determines this classification. Positive non-transfer amounts remain income, negative non-transfer amounts expense. Unclassified transfers/duplicates may still distort results and are disclosed. Future obligation reserves are not stripped by transaction classification: they remain the user's explicit dated cash commitments.

## Recommendation rules

All defaults are named service constants. The coaching horizon is as-of through as-of + 30 days, inclusive, using today_dhaka unless an internal caller supplies a test/as-of date. Safety threshold reuses the runway convention: caller-configurable nonnegative BDT, default zero.

### Cash risk

Emit at most one cash_risk. Consume the historical runway's cash_shortfall or at_risk result. If known commitments alone bring cash to or below the floor, also inspect the existing known-obligations scenario; prefer its negative result when applicable rather than duplicating the warning. Negative minima are critical; a nonnegative minimum at/below the selected floor is high. Missing balance does not become zero. Monthly scenarios expose only their existing shortfall window; a dated shortfall is shown only for the explicitly named known-obligations scenario. No extrapolated depletion day is invented.

Evidence separates starting balance/source, remaining reserve, uncertain income, minimum/end cash, cash after commitments, safety floor, scenario mode/status and supported dates. These are scenario risks, not bank guarantees or personalized safety-floor advice.

### Upcoming obligations

Group all remaining expense obligations due within the next seven days into one preparation recommendation with each original/allocated/remaining principal and due date. For later obligations inside the 30-day horizon, include an individual review when remaining principal is at least 50% of positive established starting cash. This explicit cash-relative review threshold is not a claim that the expense is discretionary or unaffordable.

Priority is high when due today/tomorrow or the grouped remaining reserve reaches/exceeds starting cash, otherwise medium. Each obligation appears in one group only. Amount is remaining principal to prepare for, not a second payment or permission to spend. valid_until is the earliest due date. Larger future obligations are not inferred when cash is unknown, but dated near-term preparation remains useful with limited data.

### Spending spike

Require the existing three-complete-month coverage gate after transfer exclusion. Compare the latest complete category month with the immediately previous complete month. A positive reference and a strict increase greater than the existing UNUSUAL_FACTOR (1.5) produces a medium review. Incomplete current-month spending is not extrapolated or compared with a whole prior month. A new category with no reference gets no invented percentage/baseline. Evidence includes both full periods, observed/reference magnitudes, deterministic percentage change and available monthly observations.

### Repeated category increase

Only the existing REDUCIBLE_CATEGORIES qualify: Food, Shopping, Entertainment, Subscription, Travel. These are potentially reducible review candidates; essential needs still come first. Require positive category evidence in all three complete months. Both later months must exceed the same earliest-month baseline by the existing INCREASE_FACTOR (strictly greater than 1.10). Emit one medium repeated_spending recommendation instead of an overlapping spike for that category. The rule detects an observed repeated increase, not overspending against a budget that does not exist.

### Unassigned savings opportunity

At most one low-priority amount is suggested, and only if:

- Three complete months have usable coverage, each has positive recorded net cashflow **and observed expenses greater than zero**. Income-only records do not establish sustainable expense coverage.
- Account cash is derived/reconciled, the historical scenario is positive, and no known cash-risk alert exists. Reported-only, missing or conflicting cash is insufficient for this amount.
- No active savings goal exists that could claim the same money. Existing goals must be reviewed first, including incomplete/fully reported but still active goals.

The cap is the minimum of cash after known commitments minus the selected floor, the existing projected low-watermark minus that floor, and the weakest positive observed monthly net. Only a strictly positive cap is offered. No uncertain scheduled income is credited. This is a one-time optional reserve, not a recurring promise or an additional amount per goal. Repeated API reads do not create additional allocations; manual action/feedback tracking is not implemented. It is not an automatic transfer.

### Savings goal risk

Use the existing goal planner for each owner-scoped active goal. Overdue targets are high, an estimated required-contribution shortfall is medium; absent coverage/savings stay unknown. Evidence contains reported saved/target amounts, remaining amount, real target date, required contribution/capacity where available and planner affordability. There is no invented savings/contribution pattern.

The persisted model and creation schema require a target date. A defensive domain helper skips an incomplete legacy goal without inventing a date/contribution, and service limitations explain such an incomplete record. No schema relaxation or migration is introduced to create undated goals.

## Priority, identifiers and evidence quality

Sort by critical, high, medium, low, then valid_until and stable id. IDs identify one risk horizon, a distinct obligation set, a category/complete month, a goal/month, or the single unassigned savings reserve/month. There is no arbitrary numeric risk score. Overlapping cash warnings merge, repeated-category reviews supersede spikes, obligation groups do not overlap, and no independent savings amount is issued for each goal.

Evidence quality is recorded, estimated or limited: explicit plan/category facts, historical/planner estimates, or a known-obligations-only scenario/limited goal data. These classes are not calibrated probability scores. Each item has deterministic title/description/action templates, source identity, structured typed evidence, as_of_date, valid_until, appropriate amount or null, assumptions and limitations.

## API contract

Authenticated GET /finance/coaching accepts:

- priority: optional exact critical/high/medium/low filter.
- safety_threshold: optional nonnegative Decimal with at most two places and existing Money limits, default 0.00.

No user-id parameter, mutation endpoint, notification delivery or unnecessary category filters. Invalid query values return 422; missing authentication returns 401. Queries remain scoped to the authenticated user and BDT-aware existing services.

Response: as_of_date, inclusive horizon period, data_status, recommendations, limitations. data_status is sufficient when starting cash and usable historical runway inputs exist; partial when some useful account/history/action evidence is available; insufficient_data when core inputs are unavailable and no actionable evidence exists. A filtered empty list does not alter coverage status. Missing recommendations are not proof of financial safety.

Each recommendation includes id, constrained type/priority/source/evidence_quality, localized-template-ready title/description/recommended_action, currency BDT, amount or null, subject, dates, typed evidence and assumptions/limitations. Decimal outputs serialize as strings. No raw ORM structures or another owner's records are exposed.

## Frontend behavior and localization

Insights adds an on-request Financial alerts & coaching section. Refresh clears stale results; native loading/disabled/error/retry states prevent duplicate requests. Cards show text priority and evidence-quality labels, subject, amount when meaningful, review-by date, source, action and links to the existing cashflow/transactions/plans workspace. Nothing pays, transfers, confirms or creates records.

Native expandable evidence displays periods, balance source/scenario, cash/reserve/uncertain income, shortfall resolution, principal breakdowns, goal and complete-month data using existing BDT/date formatting. Assumptions/limitations expand separately. Empty supported results and insufficient evidence are distinct, with a partial-data note when applicable.

All new labels, deterministic backend templates/actions/caveats and known evidence values have English/Bengali mappings in the existing translation system. User goal/obligation names are preserved, while known category labels may use the existing taxonomy translations. Cards use existing layout tokens and responsive wrapping; meaning does not depend on color. No charts, framework or provider dependency is added.

## Tests and validation

Backend tests cover cash and approaching-floor alerts; scenario deduplication; large, grouped and partially allocated obligations; candidate/full/paid/cancelled/revoked semantics; complete-month spikes and strict boundaries; missing/incomplete history; reducible-category repeated increases; explicit transfer exclusions with legacy defaults retained; savings caps/uncertain-income exclusion/active-goal conflicts/income-only/deficit/report-only/unknown cash; planner/overdue/missing-date goals; ordering, evidence, API authentication/query validation/serialization/ownership, empty states and read-only repeatability.

Frontend tests cover actions, each priority, keyboard/native evidence expansion, empty versus insufficient data, loading/error/retry and Bengali templates/caveats/user-content preservation. Desktop/mobile browser tests cover the full Insights integration, keyboard evidence, both languages, accessibility and overflow. Existing financial regression/evaluation tests remain intact. The GitHub Actions SQLite selection includes the new suite.

Validation completed:

- `python -m pytest backend/test_financial_coaching.py -q --tb=short`: 34 passed.
- `python -m pytest backend -q --tb=short`: 528 passed, 1 existing opt-in smoke skip; 7 existing Alembic configuration deprecation warnings.
- Updated CI-selected backend tests with SQLite settings: 181 passed.
- `python -m compileall backend/app`: passed.
- `python scripts/generate_frontend_contracts.py --check`: passed.
- `npm run typecheck` and `npm run lint`: passed.
- `npm test`: 60 passed across 11 files, including 9 new coaching tests.
- `npm run build`: passed.
- Focused Chrome coaching scenarios: 2 passed (desktop/mobile, both languages).
- `npm run test:browser` with Chrome: 27 passed, 5 existing duplicate mobile viewport skips; axe accessibility, keyboard and overflow assertions included.
- `git diff --check`: passed.

Initial full regression testing found an unintended transfer-flag reference in a legacy comparison helper. It was removed, preserving that helper's original behavior, and the full backend/evaluation suites subsequently passed. Initial UI test selectors exposed combined label/action text, which now has explicit spans. Browser accessibility identified action links below the touch-target size; they now have a 44px minimum height. All accessibility rules and original test assertions remain enabled.


## Limitations and future work

Coverage is observed-record coverage, not proof of complete banking data. Balances may be stale; unclassified transfers or duplicate imports may distort estimates. No new bank verification or spending/contribution history is invented. Monthly runway retains its existing uncertainty and expense-before-income assumption. The cash-relative obligation threshold and repeated-increase rules are explicit review policies, not personalized advice or evidence that essentials should be cut.

Active-goal suppression is deliberately conservative; a future goal-aware allocation budget could replace it with a shared, explicit cash-allocation model. Advice has no persisted dismissal/read/feedback state, so manual unrecorded savings reservations cannot be discovered and repeated reads are not independent saving budgets. Live queries are not versioned historical replay. Large account/goal/category histories may need batching; shared category facts retain their existing 1,000-category ranking limit. No investment, lending, external delivery, automatic matching, recurring generation, FX conversion, automated transactions/settlement, unrestricted AI agent or financial LLM calculations are included.
