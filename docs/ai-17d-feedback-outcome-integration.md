# AI-17D Feedback and Outcome Integration

Date: 2026-11-07, Asia/Dhaka. Branch: `feature/ai-17d-feedback-outcome-integration`.

## Overview and Integration Model

AI-17D connects the canonical financial review and execution plan to the existing coaching feedback and action outcome tracking lifecycle without adding new tables, migrations, or mutating ledger states.

### Key Architectural and Behavioral Properties

1. **Source Action Provenance**:
   - Financial review steps reuse original coaching recommendation identifiers via `source_action_ids`.
   - Recommendations originate deterministically from upstream engines (runway, category spending signals, scheduled obligations, goal assessment).

2. **Synthetic Identifier Boundary**:
   - Synthetic planning identifiers prefixed with `plan:*` (e.g., `plan:negative_cashflow`, `plan:emergency_reserve`, `plan:goal:*`) represent planning suggestions and synthesis groupings, not individual coaching recommendations.
   - Synthetic `plan:*` IDs are strictly rejected by the feedback submission API (`PUT /finance/coaching/{recommendation_id}/feedback`) with `404 Not Found`. Only currently valid coaching recommendation IDs can receive feedback.

3. **Existing Endpoint Reuse**:
   - User feedback is reported through the established coaching feedback endpoint (`PUT /finance/coaching/{recommendation_id}/feedback`) and retrieved via (`GET /finance/coaching/feedback`).
   - Outcome observations are retrieved via the established action outcome endpoint (`GET /finance/action-outcomes`).

4. **User-Reported Action Boundary (`acted_on`)**:
   - The status `acted_on` is a user report of action, not independent verification or proof of financial execution.
   - Neither the feedback submission nor the review step triggers any automatic funds movement, account balance mutation, or transaction creation.

5. **Observational Evidence and Scoping**:
   - Action outcome observations are derived solely from recorded evidence (authoritative accounts, transactions, and reconciled obligations) over baseline and follow-up observation windows.
   - All outcomes remain strictly owner-scoped and authenticated.

6. **Non-Failure States**:
   - Outcomes with `status="pending"` (awaiting equal follow-up duration) or `status="insufficient_data"` (e.g., unavailable verified contribution history or incomplete baseline) are valid observational states, not system failures or error conditions.

7. **Strict Non-Causal Claims**:
   - Outcomes reflect observational before/after metrics only; `causal_claim` is guaranteed to remain `false` across all outcome reports.

8. **Zero Side-Effects and Invariant Guarantees**:
   - No new database tables or schema migrations were introduced.
   - No financial mutation endpoints or automated background financial actions were created.
   - Accounts, transactions, savings goals, and scheduled cashflow obligations remain completely unmutated by review, feedback, or outcome observation calls.
