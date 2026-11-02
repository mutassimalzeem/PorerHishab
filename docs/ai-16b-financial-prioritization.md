# AI-16B: Financial Prioritization & Decision Engine

## Architecture and existing contracts

AI-16B answers which supported financial issue deserves attention first. It is a
pure layer after AI-16A: existing finance engines -> FinancialPlan ->
prioritize_financial_plan -> FinancialDecisionSet -> future AI-16C action plan
and AI-15S explanation/validation. It does not produce another set of financial
actions or change FinancialPlan's ai-16a-v1 policy.

The existing FinancialPlan contract covers composition and CoachAction-shaped
priorities but cannot express dependency links, issue categories or conflicts.
The existing schema module therefore adds FinancialPriority, PriorityConflict
and FinancialDecisionSet. Existing CoachingPriority, CoachEvidence, CoachWarning,
IntelligencePeriod and GoalPlanningOverview contracts remain authoritative.
No endpoint, database model, migration, frontend work or dependency is needed.

## Source engines and overlap boundaries

| Source | Provides | Prioritization usage |
| --- | --- | --- |
| Coaching, feedback visibility, action plan | Source urgency, visible actions, selection cap, caveats | Consume only retained AI-16A actions; no visibility or selection changes |
| Runway and cashflow forecast | Known-obligation and historical scenario cash risks | Consume AI-16A cash-risk priorities, without forecasts or arithmetic |
| Account position and obligations | Trusted/derived/reported cash and outstanding commitments | Preserve upstream evidence and uncertainty |
| Financial health | Recorded surplus-margin and estimated liquidity signals | Consume AI-16A negative-cashflow and reserve-review decisions |
| AI-15P goal planning | Capacity, accepted commitments, proposals, feasibility, milestones | Preserve the embedded overview byte-for-byte in serialized financial values |
| Savings and spending decision | Savings requirements and buffer affordability | No savings percentages, amounts or affordability calculations |
| Alerts and scenarios | Repeated alerts and isolated what-if evaluations | No repeated-alert scoring or hypothetical cash treated as available money |

AI-15O is the financial-health engine; AI-15H is the existing action-plan layer.
No income, expense, reserve, debt, contribution, cashflow, health or forecast
formula is introduced in AI-16B. Comparisons with an already recorded accepted
commitment or known-zero capacity do not calculate a new monetary result.

## Supported issue categories

| Category | Required supporting source | Meaning |
| --- | --- | --- |
| cashflow_risk | AI-16A cash-risk or negative-recorded-cashflow priority | Review cash stability constraints |
| obligation_pressure | Selected upcoming-obligation action | Review known commitments |
| liquidity_risk | AI-16A supported emergency-reserve review | Review liquidity; no reserve target is invented |
| capacity_review | Existing goal overview with goals but unavailable capacity | Establish missing planning inputs |
| goal_commitment | Positive accepted_monthly, or known over_capacity flag | Preserve/review existing commitments |
| goal_review | Existing active goal or source goal-risk signal | Review source goal feasibility |
| spending_review | Selected repeated-spending or spending-spike action | Review categories without classifying essentials as optional |
| savings_opportunity | Selected savings-opportunity action | Review the existing one-time opportunity, not a new monthly allocation |

Cashflow signals are grouped into one issue with all source evidence and source
action IDs retained. Goal-risk signals with an unambiguous existing goal ID merge
into that goal's issue. A risk signal about an accepted goal remains a commitment
review, not a second optional savings proposal. Unmapped source priorities are
explicitly excluded with a warning. Omitted AI-16A recommendations are not rebuilt.

## Versioned priority policy

Policy version: `ai-16b-v1`; source planner version: `ai-16a-v1`.

1. Apply explicit dependencies first. Among issues whose predecessors have been
   listed, preserve source urgency: critical, high, medium, low. AI-16A priority
   ordinals 1/2/3/4 map to those levels; its permitted ordinal 5 also maps to low.
2. Within urgency use the category order listed above. Existing goal priority and
   goal ID preserve AI-15P goal ordering. Remaining ties prefer recorded facts,
   derived facts, estimates, then limited evidence; stable priority IDs break ties.
3. Grouped signals retain their highest source urgency and weakest supporting
   evidence-quality label. Policy interpretation never counts as source support.
4. Capacity and over-commitment reviews are high urgency. Existing accepted goal
   reviews retain source urgency, or medium when supplied solely by the overview.
   New goal reviews follow source urgency, or medium by default.

These are qualitative product rules, not scientifically calibrated impact or
confidence scores. Internal ordering ordinals are never exported as money,
financial-health points or confidence percentages. No reversibility or financial
impact estimate is inferred where the source engines provide none.

## Dependency and conflict rules

Each issue lists blocking_priority_ids. These are attention/review and optional
funding constraints, not commands to delay bills or cancel accepted commitments.
Each relationship also has a conflict record identifying the preceding issue,
deferred issue, reason code and kind:

| Preceding issue | Deferred issue | Reason / kind |
| --- | --- | --- |
| Cashflow constraint | Optional goal/savings | stabilize_cashflow / funding_constraint |
| Cashflow constraint | Spending review | stabilize_cashflow / review_precedence |
| Known obligations | Spending review or optional goals/savings | protect_obligations / review_precedence |
| Liquidity risk | Optional goals/savings | review_reserves / review_precedence |
| Known over-capacity commitments | Optional goals/savings | resolve_capacity / funding_constraint |
| Unknown goal capacity | Optional goals/savings | resolve_capacity / funding_constraint |
| Accepted goal commitment | Optional goals/savings | review_accepted_commitments / review_precedence |
| Spending review, when cashflow risk exists | Optional goals/savings | review_spending_before_savings / review_precedence |

A review_precedence conflict does not assert an actual funding deficit. Reviewing
spending can help cover obligations: it is not itself an optional purchase.
A funding_constraint from missing capacity means funding eligibility is unknown,
not that capacity is zero. Accepted commitments, allocations and milestones are
never reduced, increased, cancelled or reassigned; changes belong to AI-15P.

## Unknown data and time consistency

Absent health or goal context remains absent. A missing overview or unmatched
goal-risk signal leaves that review with goal_capacity_unknown; it does not create a fictitious
capacity result. An insufficient-data capacity status or null capacity cannot
establish over-capacity even if an inconsistent over_capacity flag is supplied.
Known zero remains zero. A per-goal insufficient-data result remains blocked even
when overall capacity is available. Non-feasible optional goals retain goal_not_feasible.
Neither case creates a contribution or reconstructs a health score.

All top-level source profiles and dated plan evidence must match the plan date.
Evidence supporting a priority must have that date; undated support is rejected.
Historical observation periods/dates inside source evidence remain intact: an
as-of-November assessment can legitimately describe October actuals. The original
horizon is preserved, including valid same-day horizons. Mutable input models are
revalidated; mixed dates, duplicates and broken references fail explicitly.

## Evidence provenance and safety

All AI-16A evidence is copied with source, type, date, observation timestamp,
confidence and values unchanged. A source goal-overview projection exposes existing
capacity/commitment fields under ev_priority_goal_overview; no financial values are
calculated. ev_priority_policy contains the exact resulting order, reason codes,
dependencies and conflicts, explicitly typed as interpretation. Every priority
must cite actual source evidence beyond policy interpretation. New confidence
percentages are never assigned. Monetary values remain Decimal and use existing
JSON string conventions. Source assumptions and limitations remain available.

FinancialDecisionSet validates unique IDs, evidence references and dates,
dependencies that appear earlier in the order, and conflict links. The service
uses deterministic topological ordering and rejects cycles. Input objects and
adapter results are detached so consumers cannot mutate the caller's plan.

The pure service takes only FinancialPlan. Existing authenticated services must
assemble all inputs for one user before invoking AI-16A. Neither AI-16A nor AI-16B
can detect arbitrary mixed-tenant inputs; neither is an authorization boundary.
There is no database, network, LLM, random ID or current-clock access in AI-16B.

## Examples and future integration

With cash risk, spending growth and a new goal, the output order starts with the
cashflow issue, then spending review, then goal review. The goal cites the cash
and spending issues as predecessors. No saving amount changes.

With upcoming obligations and a savings opportunity, obligations take precedence.
The savings amount remains the source engine's existing one-time amount. With
reserve pressure and a new goal, reserve review precedes optional acceleration
without inventing an emergency-fund target.

With accepted commitments above known capacity, the output adds a commitment
capacity review and blocks optional funding. Accepted amounts and milestones
remain intact. With unavailable capacity, an information review replaces any
claim of over-commitment; the absent capacity stays null.

```python
plan = build_financial_plan(scoped_coaching, goal_planning=scoped_goals,
                            financial_health=scoped_health)
decisions = prioritize_financial_plan(plan)
package = decision_evidence_package(decisions)
```

Future AI-16C should consume the ordered issues and dependency graph while using
AI-15P to change goals. Future AI-15S explanations must use this produced evidence
package and pass the existing FinancialCoachValidator before display/persistence.
The adapter neither generates nor approves responses. No validator changes are
needed; tests verify that fabricated evidence IDs are rejected.

## Verification

Focused tests use isolated fixtures and can run with DATABASE_URL=sqlite:///:memory:
and AI_EXTERNAL_ENABLED=false:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/test_financial_planner.py backend/test_financial_prioritization.py -q
.\.venv\Scripts\python.exe -m compileall backend
.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py --check
git diff --check
```

The fast CI job also runs both planning suites and the existing finance regression
scope. The complete backend suite must use a separate migrated PostgreSQL test
database, as in the existing health-postgres CI job; a bare in-memory database does
not satisfy older integration fixtures. No unrelated working-tree files are staged.
