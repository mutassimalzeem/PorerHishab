# AI-15P: Personalized financial goal planning and milestones

A goal records intent; a plan records a dated, versioned estimate of how that
intent could be funded; milestones are measurable checkpoints. Feasibility is an
estimate from recorded BDT data, never a guarantee, bank decision or transfer.
The service, classifications, alternatives, financial arithmetic and explanations
are deterministic and require no LLM, external provider or background worker.

## Existing infrastructure and authoritative sources

The existing `savings_goals` table and authenticated creation/editing/list routes
remain authoritative. No parallel goal or obligation engine is introduced.

One evaluation context serves all goals in a request:

- AI-13 `monthly_history`, excluding explicitly classified transfers, supplies
  three complete calendar months of user-scoped observed income and expense.
- AI-15A/K `get_account_overview` supplies batched account reconciliation and
  trusted BDT cash, respecting the financial date. Every BDT account must be
  reconciled and reported within 30 days. Partial trusted totals are rejected.
- AI-15D `financial_runway` consumes that same account overview and history,
  avoiding duplicate reconciliation. Its conservative historical reserve reuses
  AI-15C's maximum-of-forecast-and-known-obligations overlap policy. Scheduled
  income is not added to cash or treated as reliable income.
- AI-15B `obligation_amounts_for_items` supplies batch remaining overdue
  principal after confirmed allocations. Paid/cancelled items reserve nothing;
  reconciliation metadata never creates cashflow or a repayment transaction.
- AI-11 reported goal balances and existing target values supply goal reports.
  The shared `required_monthly_contribution` helper in intelligence/goals uses
  the original inclusive-calendar-month convention and upward cent rounding.
- Latest saved AI-15O coverage/date/limitations provide supporting context.
  No score-to-feasibility mapping is used, no health evaluation is triggered,
  and absence of a health snapshot does not block otherwise sufficient planning.

AI-15E timeline and AI-15F/H/I coaching, action plans and outcomes were inspected:
these already use the sources above. The planner does not rerun a timeline or
rebuild account balances. The new overview performs no financial query per goal;
its query-count test verifies that adding goals does not multiply queries.
The existing card contribution preview is now loaded only on request instead of
running an expensive legacy forecast for every card automatically.

## Goal model and categories

Goals retain name/title, optional description, positive monetary target, nullable
reported savings, status and timestamps. AI-15P adds category, BDT currency,
priority 1-5 (1 highest), optional target date and paused status. Existing rows
migrate to savings / BDT / priority 3 with their target/progress unchanged.

Supported categories describe monetary earmarking: emergency_fund, purchase,
savings, debt_repayment, expense_reduction and custom. The existing goal model
supports monetary targets only. Debt goals track reported repayment allocations,
not lender-confirmed amortization, debt settlement or interest. Expense-reduction
goals track an earmarked savings target, not a verified monthly spending ceiling
or causal spending reduction. These boundaries are explicit in API/UI limitations.
Nonmonetary wellbeing goals, investments and financial products are not added.

## Progress and verification

Existing saved amounts and all new contribution reports are **user-reported**.
No verified savings ledger exists in the application. Consequently:

- `verified_goal_progress` is null, never a relabeled reported account/goal balance.
- Conservative `remaining_amount` is the full target. This funds the goal without
  assuming an unverified balance is available. It is a planning assumption, not
  a claim of zero verified progress.
- `reported_progress` and `reported_remaining_amount` separately expose existing
  user reports through the authoritative goal assessment.
- Reported savings are reserved against trusted cash as potentially earmarked
  money, not added as extra cash. This deliberately errs toward underallocation.
- If an existing goal balance is unknown, users must report a starting value
  explicitly, including zero when known. A first contribution cannot silently
  turn an unknown baseline into zero.
- Contributions add positive Decimal reports, cannot exceed the reported target,
  never edit account balances, and create immutable progress events. Reaching the
  target marks the goal completed as a user report, not verified bank savings.
- Already reported-complete goals receive no further allocation. Pause/resume is
  explicit; completed/cancelled goals retain the existing terminal-state rule.

Goal edits, absolute progress corrections, pause/resume, plan requests, revisions,
contributions, missed/achieved milestones and completion preserve event history.
Correcting a current report never rewrites earlier reported milestone achievements.

## Conservative monthly capacity and reserve policy

Central constants are explicit product policies, not scientifically validated
thresholds. Financial amounts/ratios use Decimal; recommended capacity rounds
**down** to cents. Required contributions round **up** to cents.

Minimum data: each of the three complete prior months must contain positive
recorded income and expenses; all BDT cash must be recently reconciled; existing
noncancelled goal earmarks must be explicitly reported. Missing data yields
`insufficient_data`, null capacity and zero recommended allocation, not a
fabricated income/balance.

Schedules alone do not prove completeness. Each evaluation requires explicit
`schedules_confirmed=true`, meaning the user reviewed that their recorded expense
schedules include known commitments. This may include an explicitly confirmed
absence of commitments. Without that confirmation the planner refuses capacity.
The confirmation is saved with the plan; it is not a bank completeness guarantee.

Define:

- I = 80% of the *lowest* observed monthly income (20% reliability haircut).
- E = the *highest* observed monthly spending; all spending is protected rather
  than assuming an essential/discretionary split that cannot be verified.
- R = authoritative runway expected-expense reserve over the next 30 days,
  inclusive, already protecting known upcoming obligations.
- O = all currently known overdue reserved expense principal.
- G = sum of reported earmarks for noncancelled goals, including completed/paused
  goals so the same reported money cannot be casually reused.
- Cash protection = R + one additional month of E + O + G.
- Free cash = max(0, trusted cash - cash protection).
- Income capacity = max(0, I - max(E,R) - 10% of I).
- Monthly capacity = floor(min(free cash, income capacity)).

The second month of protected spending is intentional emergency-reserve policy,
not an accidental addition of overlapping schedules to forecasts. No upfront
lump-sum allocation is suggested. No future income projection is a guarantee.

Hypothetical income changes (-80% to +50%) and spending changes (-50% to +100%)
are applied through the same reserve/capacity formula. Known scheduled reserves
are never reduced by a hypothetical spending cut. The saved allocation uses the
minimum of recorded capacity and scenario capacity: optimistic assumptions cannot
increase a recommended commitment beyond observed capacity. Scenario capacity is
also exposed separately. Scenarios do not modify transactions, income or expenses.

## Feasibility, deadlines and alternatives

Required monthly contribution = full conservative target / remaining calendar
months, inclusive of the deadline month, rounded up. A missing deadline leaves
the required amount null rather than inventing one month. Past deadlines are
not currently feasible; zero capacity never divides or fabricates a completion date.

Classification compares the required amount to the goal's allocated monthly share:

| Classification | Rule |
| --- | --- |
| insufficient_data | Required data unavailable, or goal inactive/reported complete |
| not_currently_feasible | Past deadline, no allocation, or required amount exceeds 150% of allocation |
| challenging | Required amount is >110% through 150% of allocation |
| feasible_with_adjustments | Required amount is >100% through 110%, or deadline missing |
| feasible | Required amount fits allocation |

Thresholds are centralized UX choices. Every status has a deterministic explanation.
A smaller proposal is shown when the deadline is unsupported, never a promise
that the original deadline can be met with that smaller amount.

Supported alternatives:

- Extend the deadline using ceil(target / proposed monthly share), capped at 120
  months; recompute required contribution using the same calendar denominator.
- Reduce the target to the proposed share times available calendar months, never
  below already reported progress; recompute through the same classifier.
- Choose the displayed smaller contribution, review discretionary spending, or
  explicitly pause a lower-priority goal. No funds or goals are diverted silently.

Every numerical alternative is recalculated through the same feasibility rules.
It does not change the goal until the user accepts it through replan. The revised
version records both the prior target and the accepted target. Original plan JSON,
prior milestones and progress events remain available.

## Multiple goals and commitments

Goal priority is user-selected, then stable goal ID breaks ties. Existing accepted
plan commitments are reserved first: evaluating another goal cannot silently
divert their money, even for a newly higher-priority goal. Unplanned goals share
the remaining pool by priority. When replanning a goal, its own old commitment
is released for recalculation while other accepted commitments remain protected.

Current proposed allocations never exceed the shared capacity. Historical accepted
plans can exceed *new* capacity after finances deteriorate; the overview exposes
that condition and recommends review, instead of silently rewriting accepted plans.
Pause/replan requires explicit user action. No currency conversion is performed.

## Plans, milestones and API compatibility

New tables: `goal_plans` (immutable calculation snapshots with increasing version),
`goal_milestones` (checkpoint status plus report timestamp), `goal_progress_events`
(immutable request/progress ledger). The full capacity/evidence context, inputs,
original target, observation date and `ai-15p-v1` version are saved in plan JSON.

Milestones are created only for a feasible, dated plan. Unsupported deadlines or
insufficient capacity do not create an attractive unfunded schedule. Monthly
checkpoints end at each calendar month end or the final deadline. Weekly checks
split each month's budget into weekly/final-month checkpoints; a five-week month
cannot exceed that month's accepted allocation. Integer-cent remainder distribution
ensures positive installments add to the target exactly, without rounding drift.
Schedules are capped at 120 months or 260 weekly checkpoints. Tiny targets skip
zero installments and retain the final deadline.

Missing contribution reports never become payments. Past pending checkpoints are
shown as missed on reads; writes/acknowledgments persist missed events. Sufficient
explicit reports mark a checkpoint `reported_completed` once with a timestamp and
stable achieved event. Historical plan milestones can be read by plan ID.

The existing `GET /finance/goals/{id}/plan` stays a compatible, nonpersistent
legacy contribution preview. Personalized snapshots use distinct existing-goal
subresources rather than duplicate goal CRUD or conflicting GET registrations:

- POST `/finance/goals/{id}/plan`: explicitly evaluate/save a personalized plan.
- GET `/finance/goals/{id}/plans/current`: latest saved plan with current milestone reports.
- GET `/finance/goals/{id}/plans`: latest 100 revisions, chronological, as originally saved.
- POST `/finance/goals/{id}/replan`: revise inputs/explicitly accept target changes.
- GET `/finance/goals/{id}/milestones?plan_id=`: current or an owned historical plan.
- POST `/finance/goals/{id}/contributions`: explicit reported progress event.
- PATCH `/finance/goals/{id}/milestones/{milestone_id}`: acknowledge a missed or already
  sufficiently reported-complete checkpoint; it cannot invent contribution money.
- GET `/finance/goals/{id}/events`: latest 200 immutable progress/request events.
- GET `/finance/goals/planning/overview?schedules_confirmed=`: active goals, targets,
  conservative remaining amounts, capacity, accepted/proposed allocations, utilization,
  overcapacity flag, and upcoming/missed checkpoints in one evaluation context.

The existing goal PATCH handles explicit pause/resume and absolute progress correction.
All new API errors use existing HTTP detail conventions (401/404/409/422); nonexistent
and foreign resources are indistinguishable. Extra client user IDs are rejected.

## Concurrency and idempotency

All planning/progress writes acquire the owned User row lock before gathering
financial state or locking a goal. Thus same-user portfolio mutations serialize;
different users remain independent. Each mutation accepts an idempotency key.
Unique (user_id, idempotency_key) protects progress events; client keys are
namespaced apart from internal stable milestone-event keys. Reusing a key with
a different goal, body, operation, milestone or deadline-clearing intent yields 409.
An identical retry replays the saved response, even if later reports changed state.

Plan uniqueness is (user_id, goal_id, version). A deterministic fingerprint reuses
an unchanged logical calculation even with a fresh request key. Contributions
and milestone changes are atomic with their events. Route error handling rolls
back the entire transaction, including a target edit preceding schedule validation.
PostgreSQL is the concurrency contract; SQLite supports focused offline tests.

Migration `f15p00000001` follows the current `f15o00000001` head. Upgrade preserves
legacy goals/progress and applies safe defaults. Downgrade removes new planning
history/category/priority fields, maps paused to active, and fills absent deadlines
with the goal creation date because the legacy schema requires a date. This
lossy downgrade policy is explicit; deployment rollback should retain a backup
if newly created optional-deadline plans must be restored. Round-trip migration
tests verify upgrade/downgrade/re-upgrade and preservation of legacy balances.

## Coaching, outcomes, frontend and security

A missed current-plan milestone may yield one stable goal-risk review. It augments
an existing risk for that goal instead of duplicating advice. Fixed checkpoint
period evidence prevents unchanged next-day reads from resurfacing dismissed advice.
The existing action plan consumes that same stable recommendation. Outcomes expose
counts of reported milestone completions with user-reported provenance; they do
not manufacture a verified before/after savings baseline or claim causality.

The Plans workspace supports category/priority/optional deadline, explicit input
review, feasibility explanations, alternatives, milestones, reported contributions,
pause/resume, scenarios, revisions/events and portfolio commitments. No unrelated
workspace redesign is introduced. English/Bengali static translations use existing
locale money/date utilities. Loading, empty, insufficient-data and error states
remain distinct. Failed contribution retries retain the same request key.
Native labeled controls, semantic headings, keyboard-operable details and existing
accessible dialogs avoid color-only status or unlabeled actions.

All goal/plan/milestone/event queries are scoped to the authenticated user. Inputs
are validated server-side with positive Decimal money, supported categories/currency,
priority/date checks and bounded scenarios. No raw transactions, account numbers,
merchant data or payment side effects are exposed in planning responses.

## Validation

Focused backend: `backend/test_goal_planning.py` and
`backend/test_goal_planning_postgres.py` cover capacity/status boundaries, missing
inputs, reserves, obligations, alternatives, priorities, weekly/monthly cent
conservation, history, explicit progress, stable coaching, contract/auth isolation,
request replay, PostgreSQL migration/concurrency/uniqueness and atomic rollback.
Frontend unit tests cover English/Bengali plans, alternatives, retries, loading,
errors, missing data and keyboard interaction. Playwright covers the authenticated
planning journey on desktop/mobile, acceptance, progress, pause/resume, revision
history, Bengali and absence of console errors. Generated OpenAPI types are checked.
The existing full PostgreSQL CI job includes these tests; the core contract job
also runs focused planning tests without optional providers.


### Recorded implementation checks (2026-11-01)

- Full backend: 773 passed, 1 opt-in live-provider test skipped, using a fresh
  migrated PostgreSQL schema; development financial rows were not modified.
- Focused planning: 33 offline/API cases and 2 PostgreSQL cases passed in the full
  run. PostgreSQL cases include migration upgrade/downgrade/re-upgrade,
  authenticated same/different-user concurrency, uniqueness and injected rollback.
- Frontend: 151 passed. TypeScript, ESLint and production build passed.
- Full Playwright: 49 passed, 5 existing duplicate mobile viewport cases skipped.
  The final immediate-progress-refresh change also passed both new desktop/mobile
  journeys in a targeted rerun with no console errors.
- OpenAPI freshness, compileall and git diff --check passed.
- Existing nonblocking notices remain: Alembic path_separator deprecation and a
  production bundle chunk over 500 kB.
