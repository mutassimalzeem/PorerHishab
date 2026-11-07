# AI-17E real-stack financial review integration

The separate real-API Playwright configuration runs one desktop browser against
Vite on 127.0.0.1:5179 and the normal `app.main:app` FastAPI application on
127.0.0.1:8019. PostgreSQL 16 runs in a uniquely named Docker container, bound
only to 127.0.0.1:55439 with temporary in-memory storage. The existing mocked
browser suite excludes this spec and keeps its existing configuration.

## Local execution

Requires Docker (Linux containers), Python 3.12, Node 24, and installed dependencies.
From the repository root, using the activated Python environment:

```sh
python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
cd frontend
npx playwright install --with-deps chromium
cd ..
python scripts/run_financial_review_e2e.py
```

On Windows the existing environment can run the last command as
`.\.venv\Scripts\python.exe scripts/run_financial_review_e2e.py`. If using an
installed Chrome, set `PLAYWRIGHT_CHANNEL=chrome` in the calling environment.

The runner refuses occupied test ports, creates the disposable database, waits
for `pg_isready`, applies `python -m alembic upgrade head`, then runs
`python scripts/seed_financial_review_e2e.py` twice to exercise seed idempotency.
It starts `python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8019`
and waits for `/openapi.json`. Playwright starts
`npm run dev -- --port 5179 --strictPort` and waits for the frontend URL.
The browser command, run from `frontend`, is
`npm exec -- playwright test --config playwright.real-api.config.ts`.
Use the runner for normal execution: these component commands require its
database and environment to already exist.

## Environment and seed

The runner overrides `DATABASE_URL` with
`postgresql+psycopg2://review_e2e:review_e2e@127.0.0.1:55439/porerhishab_review_e2e`
and sets `REVIEW_E2E_DISPOSABLE=1`. The seed checks the PostgreSQL dialect,
loopback hostname, exact database name, exact test username, and opt-in before
importing application database code. It never reads the application `.env` to
choose its target. Guard regression tests reject remote, ordinary, and
unacknowledged database targets.

`AI_EXTERNAL_ENABLED=false`, an empty `OPENAI_KEY`, test-only signing secrets and
pepper, and `NOTIFICATION_DELIVERY_ENABLED=false` are passed to child processes.
Vite receives `VITE_API_BASE_URL=http://127.0.0.1:8019`. No real LLM is needed.
No authentication override is installed: both API and browser logins use bcrypt
password verification and normal access tokens.

Synthetic accounts are `review@example.com` and `other@example.com`, password
`Review-E2E-only-123!`. The first owns zero reported cash, fixed August–October
2026 income/expense records, a synthetic laptop goal and November rent schedule.
The second has no financial records. Existing seeded users are skipped; a failed
seed transaction rolls back. To reset all data, rerun the full disposable runner.

## Checks and safety

The browser signs in, navigates to Insights, reads actual review execution steps
and their supported `source_action_ids`, reports an action using the existing UI,
and verifies the real feedback response and subsequent review refresh. Outcomes
refresh through the shared Insights revision and appear without a page reload.
The test checks observational text, `causal_claim: false`, and pending or
insufficient-evidence status. It compares accounts, transactions, goals and
schedules before/after feedback. It also checks unauthenticated rejection,
separate-user review/feedback/outcome isolation and rejection of cross-user
feedback. Synthetic `plan:*` identifiers cannot be used by the tested UI journey.
Existing backend tests cover the broader synthetic-ID and read-only invariants.
No financial, login, feedback, or outcome response is mocked.

The runner terminates its backend and removes only its unique container in a
`finally` block, including on ordinary test failure. PostgreSQL storage is tmpfs;
there are no application volumes to delete. After a hard interruption, inspect
`docker ps --filter name=porerhishab-review-e2e-` and remove only the specific
test container with `docker rm --force <exact-container-name>`. Do not run a
blanket Docker prune or remove the normal application database.

## CI and limitations

`.github/workflows/financial-review-e2e.yml` is a separate PR/main job using the
same runner and disposable PostgreSQL container. It installs Chromium and OS
dependencies, applies all migrations, and uploads retained Playwright traces on
failure. Existing CI jobs remain intact.

This checks desktop Chromium and a newly reported action, not seven days of
verified follow-up or causation. Seed amounts and dates are fixed; the normal
backend clock determines review and feedback dates. Old balances may become
stale, and missing capacity must remain unknown. If future business rules stop
producing supported advice, update the synthetic seed rather than inventing a
recommendation ID. Abrupt host termination may require the explicit cleanup
above. The build retains the existing large-JavaScript-chunk warning.

## Implementation verification (2026-11-07)

Architecture inspection confirmed AI-17D PR #66 is merged and the implementation
branch started at the current `origin/main` (`d55b403`). Application routes keep
the API → service → repository chain and normal email/password JWT authentication.
No new application endpoints, tables, migrations, or authentication hooks were needed.

Added: this document, `scripts/run_financial_review_e2e.py`,
`scripts/seed_financial_review_e2e.py`, `backend/test_review_e2e_seed_safety.py`,
`frontend/playwright.real-api.config.ts`,
`frontend/e2e/financial-review-real-api.spec.ts`, and
`.github/workflows/financial-review-e2e.yml`.
Modified: `frontend/playwright.config.ts`,
`frontend/src/components/FinancialReview.tsx`, and `frontend/src/pages/Insights.tsx`.
The application change refreshes sibling outcome panels after review feedback.

Local checks actually executed:

| Command | Result |
| --- | --- |
| `python -m pytest backend/test_financial_review.py backend/test_coaching_feedback.py backend/test_action_outcome.py -q --tb=short` | 77 passed |
| `python -m pytest backend -q --tb=short` | 1,235 passed, 1 skipped, 49 warnings (before the five new guard tests were collected) |
| `python -m pytest backend/test_review_e2e_seed_safety.py -q --tb=short` | 5 passed |
| `python -m compileall -q backend` | Passed |
| `npm run typecheck` | Passed |
| `npm run lint` | Passed |
| `npm test -- --reporter=dot` | 26 files, 189 tests passed |
| `npm run build` | Passed; existing bundle-size warning |
| `python scripts/run_financial_review_e2e.py` | 1 browser test passed, including expanded evidence rendering; container removed |
| `git diff --check` / `git diff --cached --check` | Passed |

Frontend commands run from `frontend/`; Python commands use the repository's
Python 3.12 virtual environment. Early seed/import and expectation failures were
corrected before the successful final run. Cross-user filtered outcome requests
correctly return 404, rather than an empty successful response.
The five unrelated untracked user paths listed in the task remain untouched.
