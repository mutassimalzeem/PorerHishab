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
