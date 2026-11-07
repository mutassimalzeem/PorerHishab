# AI-17G: notification delivery and retry automation

## Architecture discovered

AI-15M/N already supplies an outbox: FinancialAlert lifecycle events pass through
orchestrator.py and enqueue_single_delivery to notification_deliveries. Preferences
and eligibility control channel, severity, explicit email consent, frequency,
Dhaka/default user timezone and quiet hours. Daily digests have separate existing
digest/item records. Alert and digest POST routes schedule optional FastAPI
background dispatch. Owner-scoped delivery/history/preferences APIs and the React
Alerts history view already exist. SMTP and an in-memory test backend already exist.
The API application has no periodic scheduler/lifespan delivery loop; Docker Compose
currently provides only PostgreSQL.

The old claimant used SKIP LOCKED but committed PROCESSING without an expiry or
fencing token. Crashes stranded records, retry draining required another request,
the by-ID helper could send terminal records, and provider calls ran inside read
transactions. Digest delivery did not recheck consent. Broad SMTP exception ordering
treated permanent 5xx failures as transient and retained raw provider error text.
Uniqueness recovery rolled back the caller's entire transaction. PostgreSQL migrations
also retained an obsolete unique constraint without occurrence_count, so legitimate
repeated alert occurrences failed despite having distinct idempotency keys.

## Persistent lifecycle and compatibility

Existing API/database names are retained; no frontend contract change is needed:

| State | Meaning | Next states |
| --- | --- | --- |
| PENDING | queued or deferred by quiet hours | PROCESSING |
| PROCESSING | leased attempt | SENT, FAILED, DEAD_LETTER, SUPPRESSED, PENDING |
| FAILED | retry scheduled, not terminal | PROCESSING after next_attempt_at |
| SENT | provider accepted, or in-app record made available | terminal |
| DEAD_LETTER | permanent failure or attempt budget exhausted | terminal |
| SUPPRESSED | no longer eligible | terminal |

An expired PROCESSING claim can be reclaimed into PROCESSING with a new token,
or DEAD_LETTER when exhausted. Legacy PROCESSING rows with null expiry are
recoverable immediately. Attempt counts include abandoned provider attempts;
quiet-hour deferrals and suppressions do not consume provider attempt budget.
SENT records are never selected again. No automatic terminal requeue is provided.

Migration f17g00000001 (parent f17f00000001) adds nullable claim_token VARCHAR(36),
lease_expires_at TIMESTAMPTZ, and a status/lease_expires_at index. Existing due-work
and unique idempotency indexes are reused. Upgrade/downgrade preserve old records.
The migration replaces the obsolete logical-identity uniqueness rule with an
occurrence-aware rule consistent with the existing orchestrator. Downgrade refuses
transactionally if multiple recurrence rows cannot satisfy the old uniqueness
rule; it never deletes history. No duplicate outbox, provider, endpoint, or
notification preference model was added.

## Claims, transactions and recovery

All entry points use the same claimant, including by-ID request wakeups.
PostgreSQL SELECT FOR UPDATE SKIP LOCKED selects due PENDING/FAILED or expired
PROCESSING records in bounded batches. Claim transactions assign a UUID token,
expiry, last_attempt_at and increment attempt_count, then commit. Provider calls
occur after message preparation commits, without a database transaction.
Completion locks and rechecks status, original token and unexpired lease before
updating delivery and digest in one short transaction. A stale worker cannot
overwrite a newer result, including when the provider accepted its message.

The standalone worker claims one item immediately before processing it and repeats
up to the batch limit, avoiding leases expiring while a large batch waits for I/O.
Request-triggered batches may leave expired items for the periodic worker; expired
claims cannot send. Multiple instances can safely drain different rows. PostgreSQL
is required for supported concurrent operation; SQLite does not establish these
guarantees. SIGINT/SIGTERM stop new claims and allow the current synchronous
attempt to finish. Abrupt shutdown is recovered from the persisted lease.
The worker is a separate process, so FastAPI reload/multiple API workers do not
start duplicate schedulers. No Celery, Redis or paid infrastructure is required.

## Idempotency and ambiguous outcomes

The existing database unique key includes user, alert/digest, channel, event and
occurrence. Every retry reuses the same row/key. Savepoints recover enqueue and
default-preference uniqueness races without rolling back unrelated business work.
Message-ID and X-Idempotency-Key remain stable on retries for correlation and for
future adapters supporting provider idempotency.

SMTP does not guarantee deduplication on either header. A timeout, process death,
or lost database commit after provider acceptance is ambiguous: a recovered attempt
may send another email. A paused worker may also finish an external send after its
lease expires; fencing protects database results, not the external SMTP server.
This is bounded at-least-once attempt processing with duplicate prevention for
normal overlapping live claims, NOT exactly-once external delivery. Providers
supporting idempotency should use the stable key within their retention window.
SENT means provider acceptance, not inbox placement, reading, or financial action.

## Retry and providers

EmailSendResult carries acceptance, normalized transient/permanent category and
optional retry_after_seconds. SMTP checks recipient refusals and classifies 4xx
as temporary, 5xx as permanent, and network/disconnect/timeouts as temporary with
unknown acceptance. Unknown adapter exceptions become sanitized terminal provider
errors; transport exceptions schedule retries. Unknown backend names fail closed.
No real production provider credentials are configured by this milestone.

Delay is max(configured staged floor, initial delay * 2^(attempt-1)), plus bounded
uniform jitter, capped by the configured maximum. Retry-After is a minimum and may
exceed the local delay cap to avoid retrying before provider permission. Scheduling
is persisted in next_attempt_at and survives restarts. Maximum attempts includes
the initial attempt. Exceptions and raw provider text are never persisted or logged;
logs use delivery IDs, owner IDs, status and fixed event/category strings.

| Environment variable | Default |
| --- | --- |
| NOTIFICATION_DELIVERY_ENABLED | true; gates both creation and delivery |
| NOTIFICATION_MAX_RETRIES | 3 total attempts |
| NOTIFICATION_RETRY_BACKOFF_SECONDS | [60,300,900] staged floors |
| NOTIFICATION_RETRY_MAX_DELAY_SECONDS | 3600 |
| NOTIFICATION_RETRY_JITTER_SECONDS | 10 |
| NOTIFICATION_LEASE_SECONDS | 120 |
| NOTIFICATION_BATCH_SIZE | 20 (hard bound 100) |
| NOTIFICATION_POLL_SECONDS | 5 |
| SMTP_TIMEOUT_SECONDS | 10 per socket operation |
| EMAIL_BACKEND | test (no network delivery) |

Existing SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_USE_TLS,
EMAIL_SENDER_ADDRESS, EMAIL_SENDER_NAME and FRONTEND_BASE_URL remain supported.
Keep credentials in the deployment environment. The CLI rejects leases no longer
than four SMTP socket timeouts and nonpositive polling intervals. Socket timeouts
are per operation, not a total wall-clock deadline; use an appropriately long lease
for your provider and monitor abandoned claims. Arbitrary injected adapters must
supply their own bounded I/O.

## Local and production operation

From the repository root after activating the Python environment:

    python -m alembic upgrade head
    # PowerShell:
    $env:PYTHONPATH='backend'
    python -m app.services.notifications.worker

For a cron/service-manager invocation use --once. Linux equivalent:

    PYTHONPATH=backend python -m app.services.notifications.worker --once

Run the continuous command under your process supervisor/container service next
to the API, using the same DATABASE_URL and provider configuration. Apply migrations
before starting new workers; stop old worker versions during rollout because they
do not honor claim tokens. Set the service shutdown grace period longer than the
provider timeout/lease. Multiple supervised instances are supported. The existing
Compose database need not change; there is no application container image to extend.
A worker must actually be deployed for autonomous retries; optional API background
tasks are only latency optimizations.

This milestone drains already-created notifications; it does not introduce automatic
financial evaluation, new digest generation schedules, or financial operations.

## Eligibility, privacy and monitoring

Before sending, recheck owner-scoped source alert/digest, active alert state, current
preferences, channel consent, frequency and user quiet hours. Existing critical-alert
quiet-hour/immediate-toggle exceptions remain, but never bypass channel opt-out or
email consent. Digests additionally require daily_digest_enabled and active,
same-owner source alerts. If any digest source has become ineligible, suppress the
stale digest rather than send misleading content. Preferences changing after the
final read can still race with a send already in progress.

Existing privacy-safe email builders omit amounts, transactions and account details.
No financial evidence, body, recipient, credentials or provider exception is logged.
Claims are internal and absent from API schemas. All existing owner-scoped API
filters remain. Delivery changes no account, transaction, schedule, coaching evidence,
AI-16 review validation or authorization to execute financial actions.

Monitor existing operational counts for PENDING/PROCESSING/FAILED/DEAD_LETTER,
oldest pending age, worker process health and fixed failure log events. Persistent
PROCESSING beyond lease/poll time signals worker or database trouble. Correct provider
configuration before considering manual, owner-scoped requeue of a DEAD_LETTER row;
inspect ambiguous outcomes first. There is deliberately no unauthenticated recovery
endpoint. The development TestEmailSender retains messages in process memory and
is only suitable for tests/development, not delivery or durable auditing.

## Validation and changed files

backend/test_notification_automation.py exercises real PostgreSQL concurrent claims,
parallel provider attempts on different rows, abandoned claims, stale completion,
retry eligibility, cap/jitter/Retry-After, timeout/exhaustion, preference changes,
duplicate enqueue and caller rollback/races, migration roundtrip, owner-scoped API
access, hidden claim fields, normalized SMTP responses and sanitized errors.
Existing delivery and orchestration tests remain active.

scripts/check_notification_delivery_e2e.py uses the disposable runner database,
real JWT login and FastAPI status reads with the normal polling worker and test
provider. It verifies PENDING -> SENT, FAILED -> SENT with a stable identity,
and permanent DEAD_LETTER without real email. A test-local adapter injects failures;
no production test hooks or external credentials are introduced.
frontend/e2e/notification-delivery-real-api.spec.ts signs in through React and reads
the persisted results in the existing history UI. Existing review/coach browser
journeys remain. CI runs the focused PostgreSQL tests and lifecycle/browser runner;
the existing health-postgres job continues to run the entire backend suite.

Changed files: backend/app/core/config.py,
backend/app/models/notification_delivery.py,
backend/app/services/notifications/{dispatcher,email_sender,worker}.py,
alembic/versions/f17g00000001_delivery_leases.py,
backend/test_notification_automation.py, backend/test_notification_delivery.py,
scripts/{run_financial_review_e2e,check_notification_delivery_e2e}.py,
frontend/e2e/notification-delivery-real-api.spec.ts,
frontend/playwright{,.real-api}.config.ts,
.github/workflows/financial-review-e2e.yml, this document and the G11 audit entry.

## Executed validation (2026-11-07)

Commands run from the repository root with .venv/Scripts/python.exe unless noted:

| Command | Actual result |
| --- | --- |
| python scripts/run_financial_review_e2e.py --backend-tests backend/test_notification_automation.py backend/test_notification_delivery.py backend/test_notification_orchestration.py | 60 passed; migration upgrade/downgrade, lifecycle probe and 3 real-stack browser tests passed |
| python scripts/run_financial_review_e2e.py --backend-tests | Final full run: 1,280 passed, 1 existing skip, 57 warnings; lifecycle probe and 3 real-stack browser tests passed |
| npm run typecheck; npm run lint (frontend/) | Passed, including recheck after selector correction |
| npm test -- --run (frontend/) | 26 files, 194 tests passed |
| npm run build (frontend/) | Passed; existing >500 kB bundle warning |
| PLAYWRIGHT_CHANNEL=chrome npm run test:browser (frontend/) | 53 passed, 5 existing mobile duplicate-viewport skips |
| python -m compileall -q backend/app | Passed |
| python scripts/generate_frontend_contracts.py --check | Matched OpenAPI |
| git diff --check | Passed |

Early checks exposed and corrected an ambiguous Alerts navigation selector, an
obsolete database uniqueness constraint, and a backlog fixture that counted other
tests' intentionally pending rows. No existing tests were disabled. Disposable
containers were removed by the runner. No real email was sent.
The five unrelated untracked user paths remain preserved. This branch starts at
origin/main 539483b; the user's direct request authorizes committing, pushing and
raising a PR despite the older no-PR restriction in the pasted task brief.
