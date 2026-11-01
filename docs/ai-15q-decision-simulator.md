# AI-15Q: Financial Decision Simulator & What-If Planning

The authenticated `/scenarios` workspace tests financial assumptions against current recorded BDT finances. A scenario is an alternative set of assumptions, not a forecast, guaranteed outcome, financial advice, or instruction to move money. All arithmetic uses Python Decimal. No LLM or network provider calculates, interprets missing inputs, or executes a scenario.

## Architecture and authoritative baseline

The implementation deliberately orchestrates existing components:

| Fact or policy | Authority |
| --- | --- |
| Account balances and trusted cash | AI-15K `get_account_overview`; AI-15P additionally requires every BDT account to be trusted and verified within 30 days |
| Complete prior three months, transfer exclusion, average income/expenses | AI-13 `monthly_history` and its AI-09 forecast baseline |
| Remaining scheduled obligations | AI-15B/C reconciliation and AI-15D `financial_runway` |
| Protected savings capacity | AI-15P `build_context` and shared pure `capacity_from_facts` |
| Required contributions, accepted commitments, competition and feasibility | AI-11/13 contribution convention and AI-15P `allocations` / `assess_goal` |
| Cash projection and monthly expense-before-income minima | AI-15D runway, with an internal adjustment callback rather than a second runway engine |
| Financial health | Explicitly `not_available_for_scenario`; AI-15O's stored real snapshot is never changed |

AI-10 purchase arithmetic is not duplicated. An explicitly dated one-time purchase is represented as an additional competing goal and evaluated by AI-15P, with scenario runway shortfalls also preventing an affordable classification. Several purchases compete within one context. A windfall due after today can change projected cash but never funds current goal capacity.

`trusted_available_cash` stays the same real starting fact in both columns. Hypothetical events change `projected_end_cash` and `minimum_projected_cash`, keeping real and hypothetical cash distinct. The API also returns monthly income, expenses, recorded upcoming 30-day obligations, conservative savings capacity, free capacity after accepted commitments, and goal comparisons. Month-count runway is explicitly unavailable because the existing runway engine cannot infer an exact depletion duration from monthly history. Its checkpoint evidence and status are retained in every run.

## Typed persistence and versioning

Migration `f15q00000001` follows `f15p00000001` and creates:

- `financial_scenarios`: owner, name, description, creation time, draft/saved/archived state, revision, latest baseline reference, calculation version.
- `scenario_changes`: typed Decimal amounts/percentages, change type, BDT currency, dates, optional monthly frequency, owned goal target and description.
- `scenario_runs`: owner-scoped idempotency request, version, date/reference and immutable structured evidence.
- `scenario_comparisons`: typed Numeric baseline/scenario amounts, absolute/percentage deltas, direction, status and unavailability reason, unique per run and metric.

Core money and change assumptions are typed queryable SQL columns. JSON evidence retains the observed monthly history, capacity policy inputs, both runway checkpoint series, goal evidence, original assumptions and limitations. Decimal evidence serializes as strings. A SHA-256 reference identifies the baseline facts; the result includes its financial date and `ai-15q-v1`. Replaying a historical run returns the frozen result even after real state changes. A new key explicitly evaluates current facts. Future calculation versions must retain historical evidence/results rather than silently recomputing them.

## Supported changes

| Change | Meaning |
| --- | --- |
| `income_adjustment` | Signed BDT monthly delta, or explicit signed percentage of the observed average income; mutually exclusive |
| `recurring_expense_adjustment` | Signed monthly BDT delta; a new subscription is a positive delta |
| `one_time_expense` / `one_time_income` | Positive BDT amount on an explicit date |
| `savings_contribution_adjustment` | Signed monthly allocation delta: increases earmark additional capacity; decreases release existing accepted commitments, lowest priority first |
| `goal_target_date_adjustment` | Replacement deadline for an owned active goal; supports postponement |
| `goal_target_amount_adjustment` | Positive replacement amount, never below reported savings |
| `goal_commitment_adjustment` | Nonnegative replacement for an existing accepted goal commitment |

Recurring changes require `frequency: monthly` and may specify an inclusive end date. One-time and goal changes omit frequency/end date. Every change includes an effective date, BDT currency and optional description. The initial workspace supplies exact amounts; percentage income inputs are also supported through the API. Conflicting replacements for the same goal field are rejected. A total savings reduction cannot be combined with individual commitment replacements. Reductions cannot exceed accepted commitments or make observed income/expenses negative. Unsupported currency, nonfinite values, excessive precision, foreign targets and unknown request fields fail validation.

## Deterministic execution and date semantics

1. Lock the authenticated owner's user row following AI-15P's existing serialization convention.
2. Resolve a matching owner/key request, rejecting changed revisions, horizons or confirmations with 409.
3. Read authoritative balances, history, obligations, plans and goals.
4. Copy only plain goal and plan input values into an in-memory evaluation context. No real ORM financial entity is assigned hypothetical values.
5. Feed dated income/expense deltas into the existing runway's calendar-month segments. Monthly deltas prorate by active days; one-time expenses are reserved before that segment's income and windfalls arrive at segment end.
6. Reuse the pure AI-15P capacity policy with adjusted conservative income, protected expenses, current trusted cash, overdue obligations and reported earmarks. Protect one-time purchase cash before proposing new goal allocations.
7. Reassess goal contribution requirements, capacity and risk through AI-15P; compare baseline and scenario.
8. Atomically persist only scenario metadata, run evidence and comparison rows.

Run horizons are 1-366 days, inclusive of today and the horizon end. Effective dates must lie inside the current run's horizon; to rerun later, explicitly revise dates. Monthly summary/goal comparisons describe the horizon-end run rate, while projected cash applies dated events within each segment. A change that ends before horizon end still changes projected cash but no longer changes the horizon-end monthly rate. Goal comparisons use the original as-of contribution denominator and do not simulate phased goal schedules.

The baseline retains AI-15P's conservative policy: 80% of the minimum observed income month, maximum observed spending, protected near-term obligations, overdue bills, a spending reserve, existing earmarks and an income buffer. Hypothetical improvements can improve the scenario only; they never inflate real baseline capacity. Existing accepted commitments continue to compete according to AI-15P priority/allocation rules.

## Comparison and insufficient data

Every numeric metric has `metric`, nullable `baseline_value` / `scenario_value`, nullable `absolute_delta` / `percentage_delta`, `percentage_status`, direction, availability status and reason. Positive, negative and zero changes are distinct. Percentages are unavailable for zero, negative or missing baselines and for deadline-day comparisons. Goal numeric metrics include target amounts, required contribution, projected contribution capacity, accepted commitments and days to target; goal facts also expose dates, feasibility and risk.

Three complete prior months with positive recorded income and expense are required for monthly comparisons. Missing history never becomes an income/expense zero. Unknown, stale or conflicting cash remains null; current cash can still be known when history is missing. Goal capacity additionally requires explicit schedule-completeness confirmation and known reported earmarks (including explicit zero). Unconfirmed obligation completeness remains unavailable. Every unavailable numeric metric carries a reason. Health is `not_available_for_scenario`, rather than a fabricated health formula.

Affordability statuses are `affordable`, `affordable_with_adjustments`, `not_affordable` and `insufficient_data`. They use AI-15P's existing feasibility thresholds. Wording always qualifies the assessment with the scenario assumptions. The response explanation states: "This is a scenario based on the assumptions you selected, not a guaranteed future outcome."

## API

All paths are authenticated and owner-scoped under `/finance/scenarios`. The body cannot choose an authoritative user ID. Foreign scenarios/goals produce 404.

| Method and path | Purpose |
| --- | --- |
| GET / | List the latest 100 scenarios |
| POST / | Create a draft with name/description |
| GET /baseline | Read-only current baseline; optional `schedules_confirmed` |
| GET /{id} | Inspect saved assumptions |
| POST or PATCH /{id}/changes | Atomically replace the complete typed change list (maximum 50) |
| POST /{id}/simulate | Execute with `idempotency_key`, `horizon_days`, `schedules_confirmed` |
| GET /{id}/result | Latest frozen result, or a historical `run_id` |
| GET /{id}/comparison | Latest typed metric comparisons |
| POST /{id}/save | Save the scenario |
| POST /{id}/archive | Archive; further edits/new runs fail with 409 |

Saving a scenario does not accept a goal plan or mutate finances. Editing assumptions retains historical runs; the workspace labels old results and displays the actual run assumptions. Archived runs remain readable. Repeating a matching simulation key returns the same run even when the scenario was subsequently archived. Keys are owner-scoped; using a key for different inputs fails with 409. Owner row locking, a unique owner/key constraint, and one transaction for run/comparison writes prevent concurrent duplicate inconsistent results. A failed write rolls back the complete run. This extends AI-15P's lock-and-replay convention rather than introducing an external idempotency system.

## Examples

Rent increase:

```json
{"changes":[{"change_type":"recurring_expense_adjustment","amount":"5000.00","currency":"BDT","frequency":"monthly","effective_date":"2026-11-01","description":"Rent increase"}]}
```

Laptop in four months: create a `one_time_expense` of `60000.00` with its explicit intended purchase date and run through at least that date. No fake transaction or real savings goal is created. Existing goals compete for contribution capacity; the laptop may require adjustments even when current cash appears large.

The existing `/chat/ask` question parser has a narrow `what if` intent layer. Exact rent/income phrases produce structured monetary/percentage intent and request date/horizon confirmation. "What if I save 8000 per month?" requests clarification about total versus additional savings. Ambiguous or compound requests request clarification. Chat never automatically creates or runs a scenario.

## Frontend and safety

`/scenarios` uses the existing authenticated API client, navigation, forms, responsive table containers, retry/error handling and language setting. English/Bengali labels distinguish YOUR CURRENT FINANCES from WHAT IF - NOT REAL DATA. Users create, add/remove changes, run, inspect differences/goal results/assumptions/limitations, save and archive. Monetary deltas come directly from the backend; JavaScript only renders strings. English backend evidence remains available alongside localized explanatory copy, matching existing UI conventions.

Tests compare all real financial tables before/after execution, including seeded account, transaction, goal, obligation and health rows. They cover tenant read/run/edit failures, same-key replay after real-state changes, deterministic new-key results, explicit missing data, independent arithmetic, date proration and percentage input. PostgreSQL tests verify fresh migrations, P-to-Q downgrade/upgrade, concurrent authenticated replay, uniqueness and atomic rollback. Eight deterministic evaluations cover rent, income decrease/increase, subscription, purchase, savings increase, emergency deadline and competing goals. Frontend tests and desktop/mobile Playwright cover the workspace lifecycle.

## Limitations and future extensions

BDT only; 366-day cash projections; monthly historical resolution; no exact depletion duration or investment/tax calculations. Schedules and imported history may be incomplete. Current reported goal savings remain unverified, consistent with AI-15P; no guarantee is implied. Future salary/windfall assumptions are not current money. Goal deadline changes and monthly savings changes do not model phase-by-phase allocation schedules. Financial-health formulas are not approximated. Natural-language extraction is deliberately narrow and English-only; forms support both UI languages. There is no autonomous agent, Monte Carlo, optimization, transaction mutation, transfer or automatic goal acceptance.

Future work can add versioned pure health inputs, broader confirmed intent extraction, phased contribution schedules, longer-horizon projections and explicit multi-currency conversion when authoritative supporting services exist.
