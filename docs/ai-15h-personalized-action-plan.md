# AI-15H: Personalized coaching action plan

## Purpose and architecture

Deterministic user-scoped action planning built from financial coaching and explicit feedback. No adaptive ML personalization is implemented.

Inspected current main c57d912 and verified AI-15G PR #43 was merged. The feature uses an isolated worktree to preserve the existing reconciliation edit, untracked frontend redesign and CSV files. Inspected AI-15F/G documentation, recommendation rules and validity, schemas/routes, financial facts/signals/history/runway/goal services, fixtures, generated contracts, Insights and coaching UI, localization and browser conventions. No AGENTS.md files were present.

The read path is existing financial facts (AI-15A-E), financial_coaching (AI-15F), visible_coaching (AI-15G), then action_plan (AI-15H). The dedicated finance/action_plan.py service invokes visible_coaching once and projects its output. It performs no raw transaction queries and does not regenerate financial evidence separately. No table, migration, new completion store, model inference or LLM is needed.

AI-15F orders its feed by priority, valid_until, then ID. Its identifiers depend on recommendation type and financial subject/period; validity is checked against the Dhaka as-of date. AI-15H deliberately uses the ranking below instead of the AI-15F expiry tie-breaker, preserving the original IDs and values.

## Read model and ranking

CoachingActionPlan exposes as_of_date, data_status, actions, completed_feedback, active_count, completed_count, assumptions and limitations. Each CoachingAction includes id (the unchanged recommendation ID), recommendation_id, type, priority, one-based rank, title, description, recommended_action, amount, BDT currency, active status, source, evidence_quality, subject and the original recommendation assumptions/limitations. It omits the detailed financial evidence payload; evidence and feedback controls remain in coaching.

Sort ascending by this explicit tuple:

1. Priority: critical, high, medium, low.
2. Type: cash_risk, upcoming_obligations, goal_risk, spending optimization (spending_spike and repeated_spending share one rank), savings_opportunity.
3. Original recommendation ID in lexicographic order.

There is no random value, preference score, financial threshold adjustment or inferred category dislike. Equal-priority spending types are resolved by the ID, like every other tie.

Normally the first five active actions are returned. If more than five critical actions ever exist, all critical actions are retained and the limit expands to their count. Lower priorities never displace critical warnings. If eligible recommendations are omitted, a limitation explicitly directs users to the full coaching feed. active_count is the number actually returned, after priority filtering and the limit. An explicit priority filter can exclude other priorities; it is not a safety guarantee.

## Feedback and reported completion

The existing visible_coaching function alone decides active visibility and expiry. Dismissed, acted_on, not_relevant and still-active snoozes suppress matching current recommendations; expired snoozes are eligible again. Changed evidence follows AI-15G digest rules and can resurface advice. Stale feedback cannot resurrect stale advice or masquerade as a current completion.

completed_feedback includes only owner-scoped acted_on records with is_current=true. Each retains the AI-15G feedback fields and adds action_status=reported_done. This means the user reported completing a recommendation; no financial action was verified. No historical financial advice is reconstructed. Completion rows sort by recommendation_id for stable repeated responses. completed_count covers that current completion list independently of priority filtering, following AI-15G's unfiltered feedback history convention. The complete feedback history remains in the existing coaching UI.

## Authenticated API and contracts

GET /finance/action-plan requires existing authentication and derives ownership exclusively from get_current_user. Supported query parameters match coaching: priority (critical/high/medium/low) and safety_threshold (existing nonnegative Money, default 0 BDT). There is no user_id parameter; arbitrary query parameters never select another owner. The endpoint forwards the threshold to existing coaching and does no financial arithmetic.

Money remains Decimal and serializes to strings. data_status is unchanged from coaching, including when feedback hides every action. Backend Pydantic schemas generate frontend/src/generated/api.ts using python scripts/generate_frontend_contracts.py; --check verifies consistency. No manually maintained parallel contract is introduced.

## Frontend

Insights includes a compact Your next actions section using server ordering and rank. It shows priority, original copy/subject and available amount, relevant existing links, and expandable assumptions/limitations. Cash risks and obligations link to Cashflow (which contains runway), goals and savings to Plans, and spending reviews to Insights. Reported completion is shown separately as a count with an explicit user-report explanation. Existing coaching cards retain detailed evidence, feedback and restoration controls.

The section loads on entering Insights, uses the existing loading/error/retry resource components, and refreshes after a successful coaching feedback update. It supports English/Bengali, native keyboard links/buttons, announced loading/errors and responsive wrapping. No new financial page or dashboard redesign is included.

## Financial safety and limitations

The layer copies financial amounts and evidence quality from existing deterministic recommendations. It never calculates balances, forecasts, reserves or goal capacity; modifies accounts, transactions, obligations, allocations, goals or feedback; executes payments; or creates financial records. SQL-observer coverage rejects every INSERT, UPDATE and DELETE during plan generation, including feedback writes.

The plan reflects current evidence only, not historical replay. Completion is current matching feedback, not verified accounting. Recommendations omitted by the normal five-action limit remain available in coaching. Existing data completeness, stale cash, forecast uncertainty and user-reported goal limitations still apply. There is no notification delivery, action scheduling, adaptive personalization, hidden profile, category preference inference or persistence of plans. English API prose is localized by the existing frontend-owned copy maps; user-entered names retain their original text.

## Validation

Backend tests cover authenticated/unauthenticated responses, empty and serialized responses, stable original IDs, repeated requests, priority validation/filtering, exact threshold parity, all four feedback states, natural snooze expiry, changed/disappeared evidence, completion counts, ownership, deterministic priority/type/ID order, truncation, more than five critical warnings and absence of writes. Frontend tests cover ordering, all priorities, amounts/routes, both languages, empty/completion states, loading/error/keyboard retry and refresh after feedback. Browser coverage exercises desktop/mobile, keyboard, both languages, axe and overflow; the existing full suite remains in use. The SQLite-safe CI selection includes AI-15H.

Final validation results:

- Focused backend AI-15H: 12 passed (final run).
- Full backend regression: 564 passed, 1 existing opt-in skip. Includes PostgreSQL concurrency and Alembic upgrade/downgrade validation. Ten existing Alembic path_separator deprecation warnings.
- Python compileall over backend/app and the new backend test: passed.
- Alembic heads: f15g00000001, one unchanged head; no migration needed.
- Generated OpenAPI TypeScript contract consistency: passed after final schema annotations.
- Frontend typecheck and ESLint: passed.
- Frontend unit suite: 82 passed across 13 files, including 13 AI-15H tests.
- Frontend production build: passed.
- Focused Chrome AI-15H: 2 passed (desktop/mobile).
- Full Chrome suite: 31 passed, 5 existing duplicate viewport skips. Includes English/Bengali, native keyboard retry and navigation, axe WCAG checks and desktop/mobile overflow checks.
- git diff --check: passed.

Initial new-test fixture/type/selector failures were corrected before the final successful runs. The browser error fixture now remains failed until explicit retry, so React development-mode duplicate reads cannot consume the simulated failure. No accessibility rule was disabled.

Final architectural review confirmed no duplicated financial calculations or feedback visibility rules, missing owner scoping, financial mutations, nondeterministic sorting, critical warnings displaced by the limit, client-supplied financial results, LLM calls, new persistence or unrelated redesign/CSV changes.
