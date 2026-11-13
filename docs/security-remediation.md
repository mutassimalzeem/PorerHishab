# Security remediation

This change completes the security fixes started after the source audit. It does not certify deployed ingress, database privileges, backups, or third-party account policies.

## Authentication and recovery

New passwords use HMAC-SHA256 with the configured pepper before bcrypt. The application never verifies the lossy pepper-plus-password fallback: an old truncated hash cannot establish knowledge of the complete password. Owners of legacy accounts must recover their passwords through their registered mailboxes. Do not rotate an established pepper without a separate account migration plan.

JWTs now require expiration, subject, user identity, and credential version. Existing tokens without the version claim are rejected after deployment. Password recovery increments the user credential version and invalidates both existing access and refresh credentials.

Recovery and mailbox confirmation use random, SHA-256-hashed, purpose-bound tokens with a 30-minute expiry, a 60-second resend cooldown, one outstanding token per account/purpose, and one-use consumption. Responses never expose token values. Links keep tokens in URL fragments, which the frontend removes on opening; confirmation requires an explicit action. Financial notifications remain disabled for unverified mailboxes at both generation and dispatch, including preexisting consent/outbox records.

Apply migration f18a00000001 before starting the updated API/worker. It adds verification state, credential version, and the challenge-token table. Configure a verified SMTP transport and the actual frontend URL before enabling real recovery messages. The in-memory email adapter is for tests/development only.

## Request and financial boundaries

The admission middleware buffers at most 5 MiB before invoking framework form parsers. It counts received bytes regardless of Content-Length and limits multipart boundaries, part counts, header bytes/counts, and URL-encoded field sizes/counts. Rejected uploads never reach framework spooling. CSV processing also enforces 10,000 rows, 30 columns, and a bounded error list, with parsing/persistence moved off the API event loop.

CSV and batch classification share a five-invocation provider budget, consumed at the provider boundary even when a call fails. Financial prose validation rejects currency-prefix, currency-suffix, implicit-unit and Bengali word-amount variants. Canonical financial reviews remain deterministic and no financial execution capability is added.

SMTP STARTTLS uses a validating default SSL context. Digest email uses generic high-level notices instead of raw financial titles. Development PostgreSQL binds to loopback and requires an explicitly supplied password; changing Compose variables is not a substitute for reviewing existing database credentials.

## Running tests

From backend, use the project virtual environment to run compileall, pytest, pip check, and pip-audit. Pytest supplies synthetic credentials and creates a disposable SQLite database by default; it never reads the repository .env. PostgreSQL-specific migration and concurrency cases require an explicitly supplied PORERHISHAB_TEST_DATABASE_URL. The dedicated PostgreSQL CI job supplies its disposable service URL and executes those cases.

Optional live AI smoke tests are disabled by default. Do not point the test database variable at real data. Test artifacts and dependency-audit summaries are recorded in the PR description.

## Dependency audit boundary

## Post-Merge Follow-up Remediations

The following follow-up gaps from PR #71 were resolved:

1. **Unified Password Length Policy (Issue A)**:
   - Synchronized password policies across frontend forms and backend validation.
   - `Auth.tsx` allows passwords up to 1,024 characters (removing the old 72-character client cap).
   - `AccountRecovery.tsx` aligns with registration minimum length (8 characters) and accepts up to 1,024 characters.
   - Backend `RegisterIn`, `LoginIn`, and `PasswordReset` schemas authoritatively enforce lengths (`min_length=8` for register/reset, `min_length=1` for login, `max_length=1024` for all).
   - HMAC-SHA256 pre-hashing transparently accommodates full-length passwords up to 1,024 bytes before bcrypt processing.

2. **Decoupling Security Email Delivery from Financial Notifications (Issue B)**:
   - Account verification and password recovery challenges are independent of optional financial notifications.
   - Added `SECURITY_EMAIL_DELIVERY_ENABLED` configuration in `Settings` and production Compose.
   - Password reset and email verification emails are transmitted whenever `SECURITY_EMAIL_DELIVERY_ENABLED=true`, regardless of `NOTIFICATION_DELIVERY_ENABLED`.
   - Production deployment validation guarantees that if either notification delivery or security email delivery is enabled, an explicit non-local SMTP provider is configured.

3. **Complete Multipart Boundary and Field Limit Enforcement (Issue C)**:
   - `RequestBodyLimitMiddleware` registers `on_part_data` in the multipart parser callback mapping.
   - Accurately distinguishes file parts (`Content-Disposition: form-data; ... filename=...`) from text fields.
   - Non-file text field parts are capped at `MAX_FORM_FIELD_BYTES` (64 KiB), while legitimate file uploads up to the 5 MiB overall limit are permitted.
   - Maximum multipart part counts (`MAX_FORM_PARTS = 128`) and header limits (`MAX_HEADERS = 32`, `MAX_HEADER_BYTES = 8192`) are enforced and tested.

4. **Operational Limits for Request Buffering and Concurrent Uploads (Issue D)**:
   - Configured Uvicorn operational flags `--limit-concurrency 50` and `--timeout-keep-alive 15` in `docker-compose.prod.yml` and `backend/Dockerfile`.
   - Provided canonical reverse proxy template (`deploy/nginx/proxy.conf`) specifying `client_max_body_size 5M`, request timeouts (`client_body_timeout 15s`, `proxy_read_timeout 30s`), and per-IP connection limits (`limit_conn addr_limit 20`).
   - Added regression test `backend/test_concurrent_uploads.py` verifying that memory under concurrent uploads scales predictably within bounded limits and is completely reclaimed after completion.

5. **Explicit Rejection of Optional RAG Dependencies in Production (Issue E)**:
   - The optional Chroma 1.5.9 environment carries 4 known unresolved advisories: `PYSEC-2026-311`, `PYSEC-2026-3814`, `PYSEC-2026-3815`, and `PYSEC-2026-3813`.
   - These dependencies are strictly excluded from `backend/requirements.txt` and the production Docker image.
   - Production configuration maintains `AI_EXTERNAL_ENABLED=false` and forbids enabling the unapproved RAG stack in production environments until dependency chains are remediated or replaced.


## AI-18C.2 verification status

The application now enforces an absolute body-read deadline independently of
Uvicorn's idle keep-alive setting. Peak-allocation, real-loopback Uvicorn, separate
process RSS and isolated PostgreSQL token-lock fixtures are available; their
synthetic results do not certify full production application memory usage.

Production identity email uses SECURITY_EMAIL_BACKEND=smtp independently of
EMAIL_BACKEND=test when financial notifications are disabled. The protected
production environment must configure identity SMTP/TLS, sender identity and an
HTTPS frontend URL. Missing required settings fail startup. No real SMTP service
was tested.

The Nginx file remains a host-level template, not an active Compose service or
proof of deployed TLS/ingress limits. Certificate/domain/upstream placeholders
must be adapted, validated and enabled by the operator. Forwarded-header trust is
explicit through SERVER_FORWARDED_ALLOW_IPS and disabled by default; never trust
all peers. Do not assert deployed proxy enforcement or an absolute end-to-end
body deadline from template inspection alone.
