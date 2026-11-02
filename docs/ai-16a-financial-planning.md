# AI-16A: deterministic personal financial planning

## Repository findings and overlap boundaries

| Existing layer | Authoritative output | AI-16A boundary |
| --- | --- | --- |
| Intelligence facts, categories, snapshot and signals | Recorded aggregates, coverage, recurring/category signals | Consumed through coaching and financial health; no new spending aggregates |
| Forecasting cashflow, finance runway and account position | Scenario balances, protected commitments, trusted/derived/reported cash | Existing cash-risk recommendations retain source caveats |
| Planning savings and spending decision | Required contributions, savings cuts and caller-buffer affordability | No second savings or affordability formula |
| AI-15P goal planning | Conservative capacity, shared allocations, accepted commitments, feasibility, milestones | Embed GoalPlanningOverview unchanged |
| Financial health | Versioned component assessments and underlying evidence | Consume negative mean surplus margin and liquidity watch/strained signals |
| Financial alerts | Persisted alert lifecycle over underlying signals | Do not query/write alerts or count duplicate alerts as new evidence |
| Scenarios and scenario library | Isolated what-if evaluation and comparisons | No scenario evaluation or hypothetical allocations inside this planner |
| Financial coaching / feedback / action plan | Recommendations, visibility, completion reports, priority and type ordering | Reuse CoachingActionPlan and its pure projection |
| AI-15S Financial Coach | CoachEvidence, EvidenceType, CoachAction, CoachWarning; grounded generation and validation | Export actual plan evidence for the existing validator |

SavingsPlanResponse addresses a single savings target. PersonalizedGoalPlan and
GoalPlanningOverview address goal feasibility and shared capacity. CoachingActionPlan
already represents ranked visible actions but lacks evidence and cross-engine
planning context. FinancialPlan therefore extends CoachingActionPlan rather than
replacing it or defining a parallel action/allocation/goal system.

## Files and responsibility

- `backend/app/schemas/financial_plan.py`: composed Pydantic output; reuses action,
  goal, health, warning, evidence and period contracts; validates dates and links.
- `backend/app/services/finance/financial_planner.py`: pure composition and versioned
  priority decisions; evidence adapter for future Coach explanations.
- `backend/app/services/finance/action_plan.py`: extracts the existing projection
  into `plan_from_coaching`; existing endpoint behavior is preserved.
- `backend/test_financial_planner.py`: offline decisions, edge cases, source-engine
  integration, owner-scoped inputs, mutation isolation and Coach validation tests.
- `.github/workflows/frontend.yml`: includes planner tests in the fast backend
  scope; the PostgreSQL job already runs all backend tests.
- This document: architecture, policy and integration contract.

No endpoint, migration, persistence model or frontend change is needed. There are
no new LLM dependencies or calls. IDs reuse source recommendation/goal IDs;
evidence IDs are stable hashes of full source IDs. There is no wall-clock time,
random ID or artificial numeric confidence in the pure output. Explicit source
as-of dates determine equality. The policy version is `ai-16a-v1`.

## Policy

1. Preserve existing recommendation urgency and action selection, including every
   critical action beyond the usual five-action cap. Source action ranks retain
   their existing meaning; `priorities` adds cross-engine decision ordering.
2. Critical cash-risk recommendations come first. An existing negative recorded
   mean surplus margin creates a critical cashflow review immediately after them;
   no cashflow subtraction or forecast is repeated.
3. Within an urgency tier, rank cash risk, upcoming obligations, emergency reserve
   review, goal review, spending review, then savings opportunities. A health
   liquidity component must be available, have evidence, and be watch/strained to
   trigger reserve review. No essential-expense estimate, reserve amount, reserve
   target, savings percentage or timeline is invented.
4. Goal review is medium urgency, ordered by existing goal priority then ID.
   Existing AI-15P accepted commitments, allocations and milestones remain intact.
   A review never reallocates cash. Cash-risk and over-capacity warnings explicitly
   caution against acting on optional proposals before resolving constraints.
5. Source action amounts keep their source semantics, including one-time savings
   reserves. They are never added to monthly goal allocations. Goals and existing
   milestone dates live in the embedded overview; unknown dates remain unknown.

The horizon comes from coaching, starts on its as-of date and spans zero to 366
days, consistent with the existing inclusive date convention and maximum runway
horizon. Goal and health profiles must share the coaching as-of date. Old/future
recommendations are excluded and warned about. Duplicate source identities are
rejected. Missing sources produce explicit limitations and incomplete status;
missing capacity is never replaced with zero by AI-16A. Upstream AI-15P sentinel
values remain visible alongside their insufficient-data status.

## Evidence and financial safety

Every priority cites both supporting source evidence and the versioned policy
interpretation. Recorded aggregates are derived facts; forecast/capacity/liquidity
outputs remain estimates. The policy ordering is interpretation. Source user reports
and caveats remain in embedded schemas; they are never promoted to verified bank
facts. Decimal monetary fields stay Decimal and serialize as strings under the
existing contracts. CoachEvidence.value follows AI-15S's existing flexible payload
convention, so JSON round trips preserve serialized values rather than restoring
Python types inside arbitrary evidence dictionaries.

`build_financial_plan` receives structured outputs only: it cannot select a user,
query the database, execute a payment, persist a plan or contact a model. An
internal caller must obtain all inputs for the authenticated user through existing
services, with feedback visibility applied before calling it:

```python
coaching = visible_coaching(db, current.id, as_of=day)
goals = planning_overview(db, current.id, as_of=day,
                          schedules_confirmed=user_confirmed_schedules)
health = gather_profile(db, current.id, as_of=day)
plan = build_financial_plan(coaching, goal_planning=goals,
                            financial_health=health)
```

The pure input contracts do not encode tenant identity, so the planner cannot
validate ownership of arbitrary mixed inputs. This is an internal contract, not
an authorization boundary. No public endpoint accepting caller-supplied financial
facts was added. The existing tenant-scoped database/API paths remain unchanged.

For a future explanation, call `plan_evidence_package(plan)` and pass that exact
package through the existing generator and `FinancialCoachValidator`. The adapter
exports only evidence actually produced by the plan. It does not approve any LLM
response. Tests demonstrate that a supported amount survives existing validation
and an invented planner evidence ID is rejected. AI-15S intent routing, retry
behavior, persistence, tenant checks and execution/guarantee safety are unchanged.

## Verification

Run with `AI_EXTERNAL_ENABLED=false` and `DATABASE_URL` pointing to a dedicated
migrated PostgreSQL test database:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest backend -q --tb=short
.\.venv\Scripts\python.exe -m compileall backend
.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py --check
git diff --check
```

The full suite contains tests that use the configured database directly. For that
scope use a separate migrated PostgreSQL test database (as CI does); a bare
in-memory SQLite database cannot satisfy those integration fixtures. The focused
planner/action-plan tests provide their own isolated SQLite fixtures.

The full PostgreSQL suite and frontend checks also run in the existing PR CI.
SQLite skips PostgreSQL-specific tests; CI must supply their actual result.
