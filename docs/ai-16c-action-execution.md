# AI-16C — Financial Action Execution Plan

## Purpose

AI-16C converts the ordered issues produced by AI-16B into a deterministic sequence of user-review steps. It does not calculate new financial amounts, create new recommendations, move money, cancel goals, or execute payments.

The boundary is intentional: probabilistic AI can later explain or present the plan, while financial state changes remain behind explicit deterministic application controls and user confirmation.

## Flow

```text
AI-16A FinancialPlan
        ↓
AI-16B FinancialDecisionSet
        ↓
AI-16C build_financial_execution_plan
        ↓
FinancialExecutionPlan
        ↓
AI-15S Financial Coach / UI
```

## Contract

`FinancialActionStep` contains:

- stable step ID
- originating priority ID
- contiguous sequence number
- execution/review kind
- source priority level
- human-readable title and description
- preserved source action IDs
- evidence IDs
- prerequisite priority IDs
- explicit blockers
- `ready` or `blocked` state
- confirmation requirement
- preserved assumptions and limitations

`FinancialExecutionPlan` contains:

- `ai-16c-v1` policy version
- `ai-16b-v1` source decision version
- as-of date and planning horizon
- source data status
- execution steps
- copied evidence and warnings
- inherited limitations

## Execution safety

AI-16C is a planning layer, not an execution gateway. Every step requires user confirmation. There is deliberately no amount, payment instruction, transfer instruction, account mutation, database write, external financial API call, or LLM call in this service.

Dependencies are preserved from AI-16B. A step with a blocking priority or blocking factor is marked `blocked`; the service does not silently resolve the blocker or reinterpret missing capacity as zero capacity.

## Category mapping

| AI-16B category | AI-16C step |
|---|---|
| `cashflow_risk` | `review_cashflow` |
| `obligation_pressure` | `review_obligations` |
| `liquidity_risk` | `review_liquidity` |
| `capacity_review` | `review_capacity` |
| `goal_commitment` | `review_goal_commitment` |
| `goal_review` | `review_goal` |
| `spending_review` | `review_spending` |
| `savings_opportunity` | `review_savings` |

## Non-goals

AI-16C must not:

- recalculate affordability or savings capacity
- invent a savings amount
- modify AI-15P commitments
- cancel or reduce accepted goals
- treat unknown capacity as zero
- execute a payment or transfer
- call an LLM
- access the database directly
- introduce a new financial scoring model


## Recovery and reconciliation

PR #61 already contained the seven AI-16C implementation/documentation commits
through `cacaca2`. The local workspace was still on AI-16B, with no tracked edits
or local-only commits and no AI-16C files. The local AI-16C branch was created from
the inspected remote implementation, preserving its history. No reset, blind merge,
remote API edit, push or PR update was needed for reconciliation.

The three reported backend failures were test defects: an invalid AI-16B fixture
failed before the execution contract was exercised, a case-sensitive regex did not
match the dependency error, and a missing-field default fabricated a zero in the
no-money assertion. The corrected tests use valid upstream decisions, then attempt
interpretation-only AI-16C support; match the actual dependency error; and inspect
class-level Pydantic fields plus serialized steps for the absence of amounts.

The service now revalidates and detaches the supplied FinancialDecisionSet using
AI-16B's existing validator. It does not duplicate upstream decision rules. This
also detaches the planning horizon and arbitrary evidence payloads. The unused
schema-level factory that returned empty steps for a nonempty decision set was
removed; build_financial_execution_plan is the sole conversion service.

Execution output contracts additionally enforce confirmation, blocked-state
consistency, unique source priorities and unambiguous dependencies. Nested mutated
step instances are revalidated. Ready means ready for user review, not permission
to transfer money. Blockers are not marked resolved merely because their review
steps appear earlier. Evidence identity, dates, amounts, confidence and caveats
remain source facts; no financial amounts are calculated or added to steps.

## Mobile browser regression

The browser test mocks every API request, so its goal contribution failure is
independent of backend-only AI-16C changes. A single isolated run and ten ordinary
repeats passed, but a controlled 250 ms replan response reproduced the exact
contribution-counter timeout. The trace showed the test filling the old input
before replan completed, followed by a resource refresh replacing that form.
The new required input was empty when the click completed; native validation
prevented submission and no contribution POST was sent. API route/method matching,
goal status and production contribution handling were not the cause.

The test now waits for the refreshed revised target date before filling and
checking the contribution input. The simulated response delay remains to exercise
that boundary without UI sleeps. Production frontend, API and goal-allocation
behavior remain unchanged.

## Validation workflow

Use the repository virtual environment with AI_EXTERNAL_ENABLED=false. Focused
execution tests supply isolated fixtures. Run the full backend suite against a
separate migrated PostgreSQL test database, never against user financial records:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/test_financial_execution.py backend/test_financial_execution_extra.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest backend -q --tb=short
.\.venv\Scripts\python.exe -m compileall -q backend/app backend
.\.venv\Scripts\python.exe scripts/generate_frontend_contracts.py --check
```

The existing fast CI backend command now includes both execution suites. Frontend
checks are typecheck, lint, test, the isolated mobile goal-planning spec, the full
test:browser script and build. Tests cover blocked/ready integrity, mandatory
confirmation, evidence-only interpretation rejection, upstream input corruption,
dependency order, determinism, Decimal provenance, mutation safety, forbidden I/O
and the real AI-16A -> AI-16B -> AI-16C planning chain.

Tenant ownership remains the responsibility of existing authenticated input
assembly. This pure service is not an authorization boundary. No payment,
allocation mutation, network/LLM integration, endpoint or migration is introduced.


Recovery validation completed on 2026-11-02:

| Executed scope | Result |
| --- | --- |
| Focused execution suites | 24 passed |
| Full backend, separate migrated PostgreSQL database | 1,053 passed, 1 skipped |
| Updated fast CI backend scope | 487 passed |
| Frontend unit tests | 172 passed |
| Corrected mobile test with delayed replan | 10 repeated passes, then 1 standalone pass |
| Full desktop/mobile browser suite | 53 passed, 5 skipped |
| Typecheck, lint, build, compileall, OpenAPI freshness, git diff --check | Passed |

The initial three backend failures and the delayed-response browser reproduction
were observed failures before their corrections. All final commands completed
successfully. Existing non-failing Alembic/HTTP deprecations, jsdom canvas diagnostics
and Vite bundle-size warnings are outside this recovery change.
