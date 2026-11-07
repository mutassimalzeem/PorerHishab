# AI-18A: production configuration and deployment foundations

AI-18A supplies a deployable foundation, not approval for a public launch.
AI-18B authentication/security review, AI-18C monitoring/backups/recovery, and
AI-18D real-provider and clean-production verification remain separate stages.
No financial formulas, recommendation rules, AI-16 safety checks, or automatic
financial actions changed. No public service or real email provider was enabled.

## Configuration contract

APP_ENV accepts development (default), test, or production. Production Compose
forces production so a missing or mis-set application environment cannot select
development defaults.

CORS_ORIGINS uses a JSON array, for example:

    CORS_ORIGINS='["https://finance.example.com"]'

Entries must be HTTP(S) origins containing scheme/hostname/optional port only:
no path (including trailing slash), credentials, query, fragment, malformed port,
backslash or wildcard hostname. CORS_ALLOW_CREDENTIALS defaults to true. A literal
wildcard is rejected with credentials and always rejected in production.
Development defaults remain localhost:5173 and 127.0.0.1:5173. Production requires
an explicitly supplied nonempty list; no fallback to development origins occurs.
The real-stack runner explicitly allows its 127.0.0.1:5179 frontend.

Production also requires a PostgreSQL DATABASE_URL and three distinct random
SECRET_KEY, REFRESH_SECRET_KEY and PEPPER values, each at least 32 characters.
Development placeholders are rejected. Validation error rendering hides input
values. This is a startup configuration guard; authentication algorithms, refresh
semantics, rate limits and retention are intentionally left for AI-18B.
Do not replace an established password pepper as part of a routine release:
existing password hashes depend on it. Secret rotation requires its own procedure.

Production notification delivery is off by default in Compose. Enabling it requires
both an explicit flag and a configured non-local SMTP provider. Keep delivery off
and EMAIL_BACKEND=test throughout AI-18A. AI_EXTERNAL_ENABLED also defaults off.
FRONTEND_BASE_URL must be set to the intended public frontend URL before email
enablement in a later stage. No paid provider or new external infrastructure is
required.

## Secrets and image boundaries

Create a protected environment file outside the repository, restrict its access to
the deployment operator, and keep it outside shell history, tickets and logs.
On Linux use permissions 0600; on Windows restrict the file ACL to the operator.
The file must contain the following values (placeholders are illustrative only):

    PRODUCTION_ENV_FILE=/absolute/protected/path/production.env
    APP_ENV=production
    APP_IMAGE=porerhishab-backend:<release-tag>
    POSTGRES_DB=porerhishab
    POSTGRES_USER=porerhishab
    POSTGRES_PASSWORD=<strong-random-database-password>
    DATABASE_URL=postgresql+psycopg2://porerhishab:<URL-encoded-password>@db:5432/porerhishab
    SECRET_KEY=<distinct-random-secret-at-least-32-characters>
    REFRESH_SECRET_KEY=<distinct-random-secret-at-least-32-characters>
    PEPPER=<distinct-random-secret-at-least-32-characters>
    CORS_ORIGINS='["https://finance.example.com"]'
    CORS_ALLOW_CREDENTIALS=true
    FRONTEND_BASE_URL=https://finance.example.com
    API_PORT=8000
    NOTIFICATION_DELIVERY_ENABLED=false
    EMAIL_BACKEND=test
    AI_EXTERNAL_ENABLED=false

Generate independent random values, for example with Python's secrets.token_hex(32).
URL-encode database credentials in DATABASE_URL; POSTGRES_PASSWORD remains the raw
password. The URL must use the Compose service hostname db and match its user/db.
The same absolute file is supplied with --env-file for Compose interpolation and
as PRODUCTION_ENV_FILE for application env_file injection. Exported shell variables
take precedence over --env-file: remove stale deployment overrides before release.
Use docker compose config --quiet to validate without printing resolved secrets.
Do not paste the output of unredacted docker compose config or inspect into logs.

.env.example retains convenient development settings and documents the production
overrides without real secrets. .env, .env.prod and .env.production are ignored.
The allowlisted .dockerignore excludes root secrets, frontend/user files, vector
data and Python caches from the build context. The application image runs as UID
10001, with no repository .env copied into it. API, worker and migration services
share the existing backend/Dockerfile image. Optional external-inference/RAG
dependency provisioning is unchanged; it is disabled for this stage.

## Services and network exposure

docker-compose.prod.yml is independent of the unchanged development Compose file.

| Service | Role | Exposure / restart |
| --- | --- | --- |
| db | PostgreSQL 16, named persistent volume and pg_isready health check | Internal database network, no published port; unless-stopped |
| migrate | Explicit one-off Alembic upgrade using application image | tools profile, no restart |
| api | Normal uvicorn app.main:app on port 8000 | Host 127.0.0.1 only; unless-stopped |
| worker | Independent notification polling process | No published port; unless-stopped; 150-second shutdown grace |

API and worker share DATABASE_URL, configuration and image, but run different
commands. Both have access to the private database network and an application
network for future explicitly enabled provider access. PostgreSQL is attached
only to the internal network. A named project isolates service/volume names.

GET /health/live returns {"status":"ok"} without touching the database.
GET /health/ready executes SELECT 1 against the configured database and returns
the same success body or 503 {"status":"unavailable"}. No database URL, exception,
credential, SQL error or infrastructure detail is returned. The probe uses a
dedicated NullPool connection, PostgreSQL connect_timeout=3 seconds and
statement_timeout=3000 ms, so it does not wait on the application pool.
Readiness verifies connectivity, not migration version, provider availability,
financial correctness or worker progress.

The API container health check calls readiness. Worker startup depends on API
and database health. Docker's restart policy restarts exited processes; an
unhealthy but still running API is not automatically restarted. Worker progress
heartbeats and alerting belong to AI-18C; a running worker container alone does
not prove successful delivery. No in-process API scheduler was added.

## Explicit deployment and migration sequence

Build and deploy a named release with the protected file. The following PowerShell
helper keeps every command scoped to the same project and environment:

    $productionEnv = 'C:/protected/production.env'
    function prod { docker compose --env-file $productionEnv -p porerhishab-prod -f docker-compose.prod.yml @args }
    prod config --quiet
    prod build api

For the initial deployment:

    prod up -d --wait db
    prod run --rm migrate
    # Proceed only after migration exits successfully.
    prod up -d --wait api
    prod up -d worker
    prod ps
    prod logs --tail 50 api worker

The migration service executes python -m alembic upgrade head once. The API remains
uvicorn app.main:app --host 0.0.0.0 --port 8000 and the worker remains
python -m app.services.notifications.worker. Migrations never run inside either
startup command. Do not use a bare prod up for an initial database: it does not
run the profile-gated migration service. Do not run concurrent migrations.

For an existing deployment, first arrange a maintenance window, preserve a verified
backup and record the previous image/version. Stop existing API/worker processes
before schema updates so older claim logic cannot run during migration:

    prod stop worker api
    prod up -d --wait db
    prod run --rm migrate
    prod up -d --wait api
    prod up -d worker

Only continue when each command succeeds. Migration failure leaves API/worker
stopped until diagnosed. Do not blindly downgrade or delete volumes to recover.
Existing AI-17G downgrade limits still apply to repeated-occurrence delivery data.
Backup/restore implementation and tested rollback procedures are AI-18C work.

The API binding is intentionally loopback-only. Domain, reverse proxy and TLS
configuration are not provided here and must be reviewed before any public access.
Do not change the bind address to 0.0.0.0 as a substitute for that review. Production
credentials, backups and provider approval remain prerequisites for later stages.

## Reproducible validation

    python -m pytest backend/test_production_foundations.py -q --tb=short
    python scripts/run_production_smoke.py
    python scripts/run_financial_review_e2e.py --backend-tests
    python scripts/generate_frontend_contracts.py --check
    python -m compileall -q backend
    git diff --check

The production smoke runner uses only temporary synthetic credentials, a unique
porerhishab-prod-smoke-* Compose project, a unique image tag, a loopback ephemeral
API port, and its own named database volume. It validates Compose, builds the shared
image, migrates a clean database to head, checks real CORS/liveness/readiness,
starts continuous and --once worker processes with delivery disabled, verifies
generic database-failure readiness, then shuts down and removes only its own
containers/networks/volume in finally. It does not touch the development database.
The test image remains cached locally. A failed run reports failure and still
attempts cleanup; do not use a blanket Docker prune.

.github/workflows/production-foundations.yml runs the same smoke check on PR/main.
Existing PostgreSQL and real-stack CI jobs remain active. Generated frontend
contracts include the two new health operations; no product UI was added.

## Files and scope

Modified: backend/app/core/config.py (extends the initial user CORS edit),
backend/app/main.py, backend/Dockerfile, .env.example, .gitignore,
frontend/src/generated/api.ts, scripts/run_financial_review_e2e.py and
docs/ai-17g-notification-delivery.md.

Added: backend/app/api/health.py, backend/test_production_foundations.py,
docker-compose.prod.yml, .dockerignore, scripts/run_production_smoke.py,
.github/workflows/production-foundations.yml and this document.

The existing five unrelated untracked paths remain untouched. Work stays on
feature/ai-18a-production-foundations, based on origin/main 788dbce.


## Local validation report (2026-11-07)

| Executed command | Actual result |
| --- | --- |
| python -m pytest backend/test_production_foundations.py -q --tb=short | 28 passed (final strict-origin cases included) |
| python scripts/run_production_smoke.py | Passed on final image: Compose config/build, PostgreSQL 16 clean migration to f17g00000001, real CORS and probes, worker continuous/once startup, shutdown and generic 503 on database failure |
| PLAYWRIGHT_CHANNEL=chrome python scripts/run_financial_review_e2e.py --backend-tests | 1,306 passed, 1 existing skip, 57 warnings; notification lifecycle probe and all 3 real-stack browser tests passed |
| npm run typecheck; npm run lint (frontend/) | Passed |
| npm test -- --run (frontend/) | 26 files, 194 tests passed |
| npm run build (frontend/) | Passed; existing >500 kB bundle warning |
| PLAYWRIGHT_CHANNEL=chrome npm run test:browser (frontend/) | Final full run: 53 passed, 5 existing mobile viewport skips |
| python scripts/generate_frontend_contracts.py --check | Passed |
| python -m compileall -q backend | Passed |
| git diff --check | Passed |

The full backend run preceded two additional malformed-origin cases; the final
28-test focused run and final production-image smoke cover that stricter parser.
Existing finance, AI-16/AI-17, PostgreSQL concurrency and migration tests ran without
being disabled. An initial Compose quoting error was corrected before successful
build/deployment runs. All temporary deployment resources were cleaned up.


The first mocked browser run had one initial page-load timeout in the unchanged
scenario-library test (52 passed, 5 skipped). The complete unchanged suite was
rerun successfully (53 passed, 5 existing skips); no test was disabled or modified.
