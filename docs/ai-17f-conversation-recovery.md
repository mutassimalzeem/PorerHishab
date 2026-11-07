# AI-17F conversation recovery

## Recovery contract (design)

A logical request is owned by the authenticated user and identified by a client
UUID (`request_id`, canonical UUID text). Its unique scope is `(user_id,
request_id)`, including when the first HTTP response never supplies a conversation
ID. Different keys mean separate turns even for identical questions. The same key
with different trimmed text, language, schedule confirmation or conversation is a
409 conflict. Keys are not authorization credentials.

Received requests atomically persist their conversation (if new), user message
and `processing` turn. There is no open transaction during evidence assembly or
generation. The processing lease lasts 120 seconds. Concurrent retries receive
409 and must check status; they do not generate. Failed or expired processing
turns can be claimed with a new random lease token using a conditional update.
Completion checks that token before atomically storing the assistant message,
canonical response and `completed` state. An expired worker cannot publish an
answer after another worker claims the turn. Failures mark only the current
lease `failed`; failures after completion cannot change a completed turn.

Process death after receipt leaves a recoverable expired lease. Process death
after completion or a lost HTTP response is recovered by replaying the identical
stored response, including its original recording timestamp. Retried generation
assembles fresh server-side evidence. Replayed answers and conversation history
are explicitly historical; they do not claim to reflect current balances.

Only one processing turn is admitted per conversation. Failed turns can be
followed by a new question; older failed turns then remain visible but cannot be
retried. This avoids appending late answers behind a newer completed exchange.
Clients without keys remain compatible but cannot recover a lost first response;
the server assigns their key. The updated chat always supplies a key.

Turn status is available by owner-scoped request ID, including before the client
knows the conversation ID. Status reports retry eligibility and lease wait time.
Conversation detail includes recovery metadata on user messages and canonical
responses on assistant messages. Legacy messages have null recovery metadata.

History opens at the newest 100 messages in chronological ID order; a `before_id`
cursor loads earlier messages. Bounds are 1–200 messages per request. Conversation
listing retains offset pagination; the UI can load more than its initial ten.
Rows are retained until the owner deletes the conversation; deletion also removes
its turns. Model context is bounded to 20 messages and excludes incomplete keyed
turns. Historical text is marked as historical context, never financial authority.

One backward-compatible migration adds the turn table and nullable message
request metadata with a unique `(user_id, request_id, role)` constraint. Existing
messages and conversations are preserved. PostgreSQL concurrency tests and
migration tests must exercise the actual constraints; SQLite unit tests alone
are insufficient evidence for concurrent behavior.

## Scope and safety

No financial execution, notification automation, new chat framework or financial
calculation changes. Ownership is checked before conversation or request access.
Error messages contain no internal exception details. External AI remains optional
and disabled in real-stack tests. G09 is not marked closed until the implementation
and acceptance tests below have run successfully.

## API and UI behavior

`POST /coach/ask` accepts an optional UUID `request_id`. Existing clients still
receive the same financial answer shape, with optional `request_id` and
`recorded_at` metadata. A completed replay is byte-for-byte equivalent at the
JSON-value level to its original canonical answer; evidence retains its original
as-of dates. Request state lives at authenticated `GET /coach/requests/{request_id}`.
Missing or foreign-owner requests return 404. Active requests, changed key inputs,
and superseded retries return sanitized 409 responses. Generation/storage failures
return the existing generic 500 message; clients query status because a failed
HTTP response is not evidence that the answer was not committed.

`GET /coach/conversations/{id}` adds `limit` and `before_id`, `has_more`,
`next_before_id`, and optional per-message request state. `limit` defaults to 100
and has a maximum of 200. Messages use monotonic IDs as their append chronology;
timestamps still record when each user/assistant message was saved. Pagination
uses an exclusive ID cursor, so new appended messages do not duplicate old pages.
Conversation listing keeps `limit`/`offset`, most recently active first; activity
can reorder that list between offset requests.

The existing coach UI uses a UUID for each new submission and reuses it for a
retry. A local ref prevents rapid duplicate sends. A transport failure triggers
a status read: a completed answer is reconciled by request ID; failed/interrupted
requests expose Retry only when the server permits it; processing/unknown requests
expose Check request status. A confirmed 404 receipt permits sending the same key
again, which remains safe if the original request subsequently arrives. Unknown
network status does not permit an unguarded retry. Unresolved requests prevent
another question in that conversation until checked or recovered; New chat stays
available. Older failed turns remain visible after newer questions, with no retry.

The Ask route passes its authenticated owner ID to a separate recovery hook.
Session storage holds only selected conversation/request IDs, scoped by owner;
questions, answers, tokens and financial evidence are not stored there. Navigation
and reauthentication in the same tab restore the selected history. Existing login
sessions themselves remain memory-only. History is loaded from the server; it is
never trusted from browser storage. A recovered first request retrieves the rest
of the conversation too. Async results cannot overwrite a different selected chat.
English/Bengali status labels, keyboard submission, mobile message layout, and
the existing structured evidence renderer are retained.

## Local validation

From the repository root, using the project Python environment and Docker:

```powershell
python -m pytest backend/test_financial_coach_persistence.py backend/test_financial_coach_api.py backend/test_financial_coach_security.py backend/test_coach_recovery.py -q --tb=short
python -m compileall -q backend
python scripts/generate_frontend_contracts.py --check
python scripts/run_financial_review_e2e.py --backend-tests
```

The last command creates disposable PostgreSQL, migrates to head, runs the full
backend suite against that database, seeds deterministic accounts, and runs both
the preserved AI-17E review journey and the new AI-17F recovery journey. A narrower
run is `python scripts/run_financial_review_e2e.py --backend-tests backend/test_coach_recovery_postgres.py`.
Omit `--backend-tests` to run just the two browser journeys. Setup and cleanup
requirements are unchanged from `docs/ai-17e-real-stack-integration.md`.
Backend tests use the existing notification test backend; browser runtime disables
notification delivery and external AI. No production database or LLM is involved.

From `frontend/`:

```powershell
npm run typecheck
npm run lint
npm test -- --reporter=dot
npm run build
```

Migration `f17f00000001` upgrades `f15s00000002`; PostgreSQL tests exercise downgrade,
legacy inserts, upgrade, new receipts, downgrade preservation and re-upgrade.
The existing full PostgreSQL CI job discovers the new unit/concurrency/migration
tests. The existing real-stack CI workflow now runs both browser specs through
its existing runner and retains failure traces. No additional CI job is needed.

The recovery browser test resumes a seeded receipt with an expired lease through
normal login and the existing chat UI. It checks canonical replay and ordered
history, then intentionally discards a client read *after* the actual backend
completion to prove status recovery without a second question or answer.
Persistence and status endpoints are never mocked.

## Limitations

- Recovery is explicit; there is no background job, heartbeat or automatic retry.
  A crashed worker may require waiting for its 120-second lease. Optional provider
  calls already have bounded timeouts. Fencing prevents stale publication after
  takeover, but a slow expired worker may still finish computation and discard it.
- Only the newest incomplete request can resume. Once a new question follows a
  failed one, ask it again as a new logical turn if needed. An expired processing
  receipt must first be resumed using its original key.
- Legacy messages cannot retroactively acquire reliable request identity. A
  legacy trailing user question is shown with unknown status; new questions use
  durable keys. Legacy clients omitting keys cannot recover a lost first response
  by identity and should adopt the new field.
- Retention is owner-controlled deletion, not an automatic expiry policy. Long
  histories use bounded pages and bounded model context; earlier messages are not
  silently deleted. Replayed financial answers are historical, not refreshed advice.

## Verification record (2026-11-07)

- Started at merged AI-17E `origin/main` commit `3500f15` on
  `feature/ai-17f-conversation-recovery`.
- Focused original coach suites plus recovery tests: **48 passed**. These include
  an initial receipt rollback, an error after assistant commit, and releasing the
  read transaction before generation.
- Full backend suite through disposable PostgreSQL runner: **1,255 passed,
  1 skipped**, before the three final boundary tests were added; those were then
  included in the successful focused run. Migration/concurrent-reclaim tests also
  ran independently: **2 passed**.
- Frontend full suite: **194 passed across 26 files**. Typecheck, lint, production
  build, and the final focused 14-test chat suite passed. The existing bundle-size
  warning remains.
- Real-stack Playwright: **2 passed**, preserving AI-17E and adding AI-17F. The
  disposable container was removed after execution.
- Backend compilation, generated contract check, and Git diff whitespace check
  passed. Existing unrelated untracked files remain untouched.

Files added: `alembic/versions/f17f00000001_coach_turn_recovery.py`,
`backend/test_coach_recovery.py`, `backend/test_coach_recovery_postgres.py`,
`frontend/src/lib/useCoachRecovery.ts`,
`frontend/e2e/coach-recovery-real-api.spec.ts`, and this document.

Files modified: backend coach API/model/schema/persistence service;
`backend/test_financial_coach_review.py` (exclude recovery metadata from the
financial-table snapshot); frontend App/Ask/FinancialCoach, API methods,
generated contracts, localization entries and chat tests; both Playwright
configurations; the existing seed/runner scripts; and the G09 audit entry.
The existing workflows discover the added tests without changing job structure.
