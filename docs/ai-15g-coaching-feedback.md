# AI-15G: coaching feedback, dismissal and relevance tracking

## Architecture and inspection

Implemented on feature/ai-15g-coaching-feedback from latest origin/main 391761a. Inspected AI-15F source and notes, authenticated routes, all recommendation identifiers, schemas, model exports, ownership and allocation constraints, Alembic chain/environment, existing database fixtures and migration/concurrency tests, CI selection, FinancialCoaching, API client, generated contracts, translations and desktop/mobile browser conventions. There were no AGENTS.md files. Untracked frontend redesign work and CSVs remain untouched.

The AI-15F financial rules and calculations remain unchanged and read-only. Exceptionally long compound identifiers are compacted as described below. A separate coaching_feedback service recomputes its current recommendations, joins owner-scoped feedback, and applies visibility. It never changes the runway, thresholds, category rules, accounts, transactions, balances, obligations, allocations or savings goals. Existing intelligence and legacy coach endpoints are unaffected.

## Persistence and migration

Alembic f15g00000001 follows f15b00000001. Upgrade creates coaching_feedback; downgrade drops only this new table. Fields: integer id and user_id, recommendation_id (300 characters), SHA-256 evidence_key (64 characters), constrained status, nullable snoozed_until, UTC created_at and updated_at. The user foreign key references users.id with ON DELETE CASCADE. Unique (user_id, recommendation_id) enforces one current record per owner/recommendation. Indexes support user reads and user/status queries. Check constraints enforce the four states and require a date exclusively for snoozed rows.

Deploy with `python -m alembic upgrade head` before serving the new API. The migration is exercised against an isolated PostgreSQL schema, including downgrade/upgrade preservation of existing users, constraints, indexes, concurrent writes and cascade deletion. The implementation does not migrate the developer's normal database automatically.

PostgreSQL and SQLite use native INSERT ON CONFLICT DO UPDATE. Concurrent submissions keep one row, preserve created_at and update status, date, digest and updated_at. Last database writer wins. No recommendation payload or free-form notes are stored; this is current state, not an event log. Restore deletes the state and its timestamps.

## Identity and current advice

Existing identifiers distinguish cash-risk date horizons, obligation item sets, category/evidence months, goal/month and the unassigned reserve/month. Identifiers longer than 300 characters (large obligation sets) use a deterministic SHA-256 of the full original key, preserving the original source_id and evidence. Normal existing identifiers remain unchanged. This avoids truncation or database failures for large current recommendation sets. Every PUT regenerates the authenticated owner's unfiltered recommendation set at the specified safety threshold. Missing or expired IDs return 404. Client financial fields and user IDs are rejected rather than trusted. URL-encode IDs, particularly comma-separated obligation clusters.

A digest additionally binds feedback to type, priority, amount and complete structured evidence. This prevents an old dismissal from hiding materially revised facts or a worsening warning. For obligations, the rolling presentation period is excluded from the digest, so an unchanged obligation remains snoozed across midnight; due dates, amounts, cash and priority still participate. For other types the evidence period participates. A new month/horizon has its own existing identifier. Changed evidence can therefore resurface advice even before a snooze expires. This is a conservative visibility rule, not adaptive financial calculation.

Historical records include is_current=false when the ID is no longer generated, expired, or its digest differs. They are never represented as current financial advice. No title similarity, category preference or opaque profile is inferred. A change of safety_threshold may change whether a feedback record applies; clients must use the same query context when submitting and reading.

## Lifecycle and snooze expiry

- dismissed: hide the same still-current evidence until restored or facts change.
- acted_on: record the user's report and hide the same still-current evidence. No payment, transfer, settlement or goal contribution is verified or performed.
- not_relevant: suppress only the same current evidence. Do not infer dislike of a category or change thresholds.
- snoozed: hide matching current evidence while snoozed_until is later than today's Dhaka date. It becomes visible at the start of that date; no scheduler or write-on-read is needed. The row remains history with is_hidden=false.
- restore: delete the authenticated owner's state. Advice returns only if the deterministic generator still produces it.

Snooze accepts tomorrow through 90 calendar days from today, inclusive, using Asia/Dhaka. Missing, malformed, past, same-day and over-limit dates are rejected; dates with any other status are rejected. Expired feedback is retained until explicitly cleared or overwritten. A critical risk with a new horizon or changed evidence resurfaces independently of earlier dismissals.

## API contract

All routes require existing authentication. No user_id parameter is accepted.

- GET /finance/coaching: retains priority and nonnegative Money safety_threshold query options. recommendations contains active current advice only; feedback contains all owner's current-state history, independently of the priority filter. Original coverage status and limitations remain intact even if every recommendation is hidden.
- GET /finance/coaching/feedback: returns the owner's feedback list, newest update first. Optional safety_threshold is used when evaluating current/hidden flags.
- PUT /finance/coaching/{recommendation_id}/feedback: body `{ "status": "dismissed" }`, or `{ "status": "snoozed", "snoozed_until": "YYYY-MM-DD" }`. Supports optional safety_threshold. Returns the updated feedback record. Validates current advice before upsert. Invalid bodies/query values produce 422; unavailable advice produces 404.
- DELETE /finance/coaching/{recommendation_id}/feedback: idempotent 204, scoped strictly to authenticated owner. Also permits removal of stale history; it never recreates advice. An unknown ID is a harmless no-op and cannot remove another owner's state.

Feedback records expose recommendation_id, status, snoozed_until, created_at, updated_at, is_current and is_hidden. IDs may coincide across users, but unique ownership scopes, API queries and server regeneration isolate them. Internal digests and database row/user IDs are not returned. TypeScript contracts are generated from FastAPI OpenAPI.

## Frontend and accessibility

Existing Insights coaching cards offer Mark as done, Dismiss, Not relevant and Snooze. Snooze opens a labeled native date input with required/min/max validation. Each recommendation has independent disabled/loading state, announced errors and an explicit retry. Successful writes refresh the feed and announce that financial records are unchanged. Refresh errors remain retryable because PUT/DELETE are idempotent.

An expandable history shows the recommendation type, reported status, update date, snooze date, stale/changed notices, expired snoozes and a restore control. It intentionally does not reconstruct old financial advice or persist sensitive titles/evidence. User-provided goal/obligation names in current advice retain their original contents. All new copy has English/Bengali translations. Native controls work with keyboard input; status and errors are announced, touch controls are at least 44px, and actions wrap on mobile using existing styles.

## Validation

Backend coverage includes authentication, creation/upsert, restoration and reappearance, owner isolation, same ID across owners, stale/expired/arbitrary IDs, strict body validation, status/date boundaries, natural Dhaka-day expiry, changed evidence, custom threshold scope, all four suppressions and SQL write observation proving no financial tables are mutated. Existing AI-15F generator tests remain unchanged. Real PostgreSQL tests exercise concurrent duplicate writes, uniqueness/foreign key/index properties and actual Alembic upgrade/downgrade.

Frontend tests cover each control, refresh/restore, per-card loading, failure/retry, labeled date selection and keyboard submission, empty/stale/expired history and English/Bengali copy. Browser tests cover feedback lifecycle, keyboard, expanded history, native date form, both languages, axe accessibility and overflow on desktop/mobile. The SQLite-safe backend suite is added to CI; PostgreSQL integration tests retain the repository's existing local database convention.

Final validation results:

- Full backend regression: 552 passed, 1 existing opt-in skip. Ten Alembic configuration deprecation warnings (same existing missing path_separator setting, now also exercised by the new migration roundtrip).
- Exact CI-selected backend suite under SQLite with AI_EXTERNAL_ENABLED=false: 204 passed.
- Focused coaching/feedback suites: 57 passed, including large obligation identifiers and new risk horizons.
- Real PostgreSQL concurrency/migration test: passed; also included in the full backend run.
- Frontend unit tests: 69 passed across 12 files.
- TypeScript typecheck, ESLint and production build: passed.
- Complete Chrome Playwright suite: 29 passed, 5 existing duplicate mobile viewport skips; includes English/Bengali, keyboard, axe and overflow checks.
- Generated API contract check: passed.
- git diff --check: passed.

The first new mobile browser test measured the language-switch transition before it finished, producing a transient contrast failure in the existing language buttons. Matching the existing test's animation wait resolved it; all original accessibility checks remain enabled.

## Boundaries and limitations

Feedback represents user reports only. It does not verify a financial action or modify facts, categorization, forecasts or goals. No ML, adaptive thresholds, notifications, profiling, free-text notes or recommendation history/event sourcing is introduced. Current financial data is recomputed rather than stored.

Evidence changes deliberately resurface advice, which can be more conservative than a user's requested snooze. History is one latest state per ID and uses generic recommendation-type labels; clearing it is permanent. Reads are not historical replay. History is unpaginated for this MVP; large histories may need pagination and retention policy later. Large compound IDs are deterministically compacted before feedback persistence. The service supports this project's PostgreSQL database and SQLite tests. Production migration execution remains a deployment operation.

Future personalization should be a separate documented/tested policy and must preserve critical warnings and financial calculations. README now records AI-15F as merged in PR #42. No merge is performed for AI-15G.


## File inventory

Created:
- alembic/versions/f15g00000001_coaching_feedback.py
- backend/app/models/coaching_feedback.py
- backend/app/services/finance/coaching_feedback.py
- backend/test_coaching_feedback.py
- backend/test_coaching_feedback_integration.py
- frontend/src/test/coaching-feedback.test.tsx
- docs/ai-15g-coaching-feedback.md

Modified:
- backend/app/models/__init__.py
- backend/app/schemas/coaching.py
- backend/app/services/finance/coaching.py
- backend/app/api/coaching.py
- frontend/src/components/FinancialCoaching.tsx
- frontend/src/lib/api.ts
- frontend/src/lib/translations.ts
- frontend/src/styles.css
- frontend/src/generated/api.ts
- frontend/e2e/finance.spec.ts
- .github/workflows/frontend.yml
- README.md
