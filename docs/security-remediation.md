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

The production requirements were upgraded and audited independently. The optional legacy RAG environment still contains Chroma 1.5.9, for which pip-audit reports five entries representing four unique advisories with no patched version listed (PYSEC-2026-311, PYSEC-2026-3814, PYSEC-2026-3815, PYSEC-2026-3813). Chroma is absent from requirements.txt and the default production image; it is installed only by requirements-rag.txt and has no active HTTP retrieval caller. Do not treat the optional RAG stack as production-approved. Its remaining advisories require upstream remediation or a separate backend migration.
