# পরের হিসাব — PorerHishab

**আজকের খরচ, আগামীর পরিকল্পনা।**

PorerHishab is a Bangladesh-first personal finance coach that helps users understand their current financial position and work toward knowing what they can safely spend after accounting for upcoming obligations and expected income.

The product direction is a Bangla-first AI financial coach: **Know what you can spend after accounting for what comes next.** The current repository includes an English/Bengali finance workspace, deterministic financial intelligence, and obligation-aware spending scenarios. Full Bangla/Roman Bangla conversational understanding remains a product goal.

## Implementation status

### Implemented

- JWT access/refresh authentication and user-scoped transaction access.
- CSV transaction ingestion, transaction creation/listing, filtering, search, and category corrections.
- Categorization using merchant preferences, deterministic rules, and validated LLM fallback.
- Financial analytics: income, expenses, savings rate, monthly and month-over-month breakdowns, categories, merchants, recurring charges, cashflow history, and budget baselines.
- Finance Q&A using exact date-scoped SQL aggregates and structured coverage; optional semantic retrieval remains isolated.
- Budget forecasting from historical and recent monthly spending, with category forecasts.
- Savings goal planning, persistent user-reported goals, deterministic recommendations and optional AI savings actions.
- Deterministic proactive insights and optional AI presentation grounded in analytics.
- Shared financial intelligence with coverage-aware facts, signals, and explanations.
- Scheduled income/expense management and caller-supplied-balance cashflow and spending scenarios.
- Account balance reconciliation from reported balances, opening balances, and recorded transactions (AI-15A).
- Transaction-to-obligation reconciliation with reviewed candidates, explicit allocations, partial payments, remaining amounts, and retained revocation history (AI-15B).
- React + TypeScript Khata workspace with English/Bengali translations and responsive finance workflows.
- PostgreSQL models, Alembic migrations, and backend unit/API/integration tests.

The coach APIs provide deterministic date-aware chat, savings recommendations,
proactive insights, persistent self-reported goals, scheduled cashflow CRUD, and opt-in obligation
scenarios. These work without an external AI provider. Optional categorization and wording use a
configured compatible provider when explicitly enabled. See [AI coach APIs and setup](docs/ai-coach.md)
for endpoint examples, assumptions, migration instructions, privacy and offline testing.

### AI-15B: obligation reconciliation

The Cashflow workspace lets users review candidate transactions, confirm allocations, track partial-payment progress, and remove allocations while retaining history. Multiple transactions can settle one obligation; a transaction can have only one active allocation. Partial payments preserve the original scheduled amount, and future obligation reserves use the unpaid remainder.

Matching is deterministic and user-scoped. Defaults are an inclusive seven-day date window and BDT 0.00 amount tolerance, configurable through the API. Amount and direction are required signals; category and merchant/description text provide supporting evidence. Cancelled obligations and allocated transactions are excluded. Suggestions never allocate money or mark an obligation paid automatically.

Full settlement requires explicit confirmation. Existing manual paid actions remain supported for items without reconciliation history. Reconciliation uses transaction principal, excludes separate fees, and supports owned BDT accounts and unlinked imports assumed BDT. Splitting one transaction across obligations and foreign-currency conversion are unsupported.

See the [AI-15B implementation report](docs/ai-15b-obligation-reconciliation.md) for matching rules, API parameters, ownership/concurrency safeguards, migration details, and validation results.

### Release status

- AI-15B is implemented on `feature/ai-15b-obligation-reconciliation`; review is tracked in [PR #37](https://github.com/mutassimalzeem/PorerHishab/pull/37).
- Production deployment and banking integrations remain future work.


### Known cashflow limitations

- Forecasts use simple historical monthly averages; they are not seasonal or trend-adjusted predictions.
- Missing calendar months between the first and last usable transaction months count as zero activity. Incomplete transaction imports can therefore distort averages.
- The API uses a caller-supplied starting balance and does not reconcile it with bank, bKash, Nagad, or other account balances.
- Transactions are pooled across the authenticated user's accounts; account-specific forecasts are not supported.
- Cash depletion is estimated at monthly resolution from projected ending balances, not as an exact date or time.
- The `healthy`, `break_even`, and `at_risk` labels describe average net cashflow. They are not a guarantee that a particular purchase is safe.
- A forecast based on a short history can be unreliable. Historical coverage is returned to help users understand this limitation.

### Planned

- Full Bangla/Roman Bangla interaction. The React frontend now lives in `frontend/`; English questions and Bangla-ready content are supported.
- MFS SMS and bank PDF ingestion, banking integrations, and automatic syncing.
- Broader safe-to-spend support using verified account data and more complete obligation coverage.
- WhatsApp/Messenger delivery, household tools, and production deployment.

[FEATURES.md](FEATURES.md) describes proposed product directions and a roadmap, including integrations and pricing that are not shipped capabilities.

## Product direction

The historical view asks: **Where did my money go?**

The forward-looking view asks: **What can I safely spend next?**

Positioning examples for future decision support include:

- “Can I spend ৳2,000 today?”
- “How much will remain after my upcoming bills?”
- “How much can I save this month without running short?”
- “Will my money last until my next income?”

Current scenarios account for recorded scheduled obligations and caller-supplied balances. They cannot guarantee spending safety when imports, upcoming bills, or income expectations are incomplete.

## Architecture

The current API entry point is `backend/app/main.py` (`app.main:app`). Authentication and several legacy endpoints remain in this module; additional routes live in `backend/app/api/`.

```text
PorerHishab/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/             # Transactions, insights, chat, forecast, planner
│   │   ├── core/            # Settings, authentication dependencies, database
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic requests and responses
│   │   ├── repositories/    # User-scoped persistence and queries
│   │   └── services/        # Ingestion, analytics, finance, RAG, forecasting, planning, AI
│   ├── test_*.py
│   ├── requirements.txt
│   └── Dockerfile
├── alembic/versions/
├── docs/
├── scripts/check_uvicorn.py
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

The Python import package remains `app`. The distribution name is `porer-hishab-backend`; `porer_hishab` is the convention for future brand-specific Python identifiers. No source package rename is needed.

Core backend tools include FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Alembic, pandas and Uvicorn. Optional provider/RAG dependencies are separated into `backend/requirements-ai.txt` and `backend/requirements-rag.txt`; they are unnecessary for core coach APIs.

`architecture.md` is a target layout rather than an exact listing of implemented files.

## API surface

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/register`, `/login`, `/refresh` | Authentication |
| GET | `/me` | Current user |
| POST | `/upload-csv` | CSV ingestion |
| GET | `/transactions`, `/transactions/me` | User transactions |
| POST | `/transactions` | Create a transaction |
| PATCH | `/transactions/{transaction_id}/category` | Correct a category |
| GET | `/search`, `/summary`, `/categories/summary` | Legacy search and summaries |
| GET | `/insights/overview` | Combined analytics |
| GET | `/insights/summary`, `/insights/monthly`, `/insights/month-over-month` | Summary and monthly comparisons |
| GET | `/insights/categories`, `/insights/merchants`, `/insights/recurring` | Spending analysis |
| GET | `/insights/cashflow`, `/insights/budget-baseline` | Historical cashflow and budget baseline |
| GET | `/insights/ai` | AI financial insights |
| POST | `/chat/ask` | Finance Q&A |
| GET | `/forecast/budget` | Historical-spending budget forecast |
| GET | `/forecast/cashflow` | Historical monthly cashflow projection |
| POST | `/planner/savings` | Savings goal plan |
| POST | `/planner/savings/coach` | Plan plus AI guidance |
| GET | `/finance/intelligence` | Shared coverage-aware financial intelligence |
| GET, POST | `/finance/scheduled-cashflow` | List or create scheduled income/expenses |
| GET, PATCH, DELETE | `/finance/scheduled-cashflow/{item_id}` | Read, update, or delete a scheduled item; reconciled history is protected |
| GET | `/finance/scheduled-cashflow/reconciliation` | Paged reconciliation overview |
| GET | `/finance/scheduled-cashflow/{item_id}/matches` | Explainable transaction candidates and allocation history |
| POST | `/finance/scheduled-cashflow/{item_id}/matches/{transaction_id}/confirm` | Explicit allocation and optional full-settlement confirmation |
| DELETE | `/finance/scheduled-cashflow/{item_id}/matches/{transaction_id}` | Revoke an allocation while retaining history |
| GET | `/accounts/{account_id}/balance/reconciliation` | Compare reported and transaction-derived account balances |
| PATCH | `/accounts/{account_id}/balance`, `/accounts/{account_id}/balance/opening` | Update reported or opening balance evidence |

See `/docs` for current request parameters and response schemas. Existing API paths are preserved by the rebrand.

## Local development

The repository root is the canonical working directory.

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/mutassimalzeem/PorerHishab.git
cd PorerHishab
python -m venv .venv
```

Activate the environment:

```powershell
.venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

Install the existing dependencies and editable backend package:

```bash
python -m pip install -r backend/requirements.txt
python -m pip install -e .
```

Copy `.env.example` to `.env`, then configure the environment locally. Do not commit credentials. Settings resolve `.env` from the repository root, independent of the shell's working directory. Preserve existing database connection values during the rebrand.

```bash
docker compose up -d
alembic upgrade head
alembic current
alembic check
python -m pytest backend -q
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`, with documentation at `http://localhost:8000/docs`. Database-backed tests require PostgreSQL. The historical live embedding smoke is opt-in (`RUN_LIVE_AI_TESTS=1`); the normal test suite uses no external AI provider. Optional RAG packages are needed to import historical RAG tests.

`python scripts/check_uvicorn.py` provides a startup smoke check. From `backend/`, the Alembic shim and pytest bootstrap also support local commands, but the repository root remains the recommended starting point.

## Storage compatibility

The rebrand changes display names and package metadata, not persistence identifiers:

- PostgreSQL database and role: `zyra`.
- Existing Compose container: `zyra-db`; service: `db`.
- Existing Compose volume key: `zyra_postgres_data`.
- Existing Chroma collection default: `zyra_transactions`, stored under `data/chroma`.

These are **legacy storage identifiers retained for compatibility**. Keep the current checkout directory and Compose project identity when using existing local volumes: a different directory/project name can select a different Compose-prefixed volume even if the volume key is unchanged.

Storage identifiers remain compatible. Scheduled items use `scheduled_cashflow_items`, savings plans use `savings_goals`, and AI-15B adds `obligation_allocations` through migration `f15b00000001` after AI-15A's `8d51117bc8d5`. Historical migrations are unchanged.

Apply `alembic upgrade head` before running the updated API or database-backed tests: allocation-aware queries require the new table. The AI-15B downgrade drops allocation history and its helper constraints while preserving scheduled items and transactions. Upgrade/downgrade is tested in an isolated PostgreSQL schema.

The historical development branch name `feature/zyra-v2` and the historical report in `docs/db-batch-db08-db10-status.md` retain their original names for accuracy.

After changing distribution metadata, refresh the editable installation with `python -m pip install -e .`. Generated metadata such as the old `zyra_backend.egg-info` directory is tooling output, not a Python source package; do not edit it by hand.

## CSV input

The upload route requires an `amount` column and accepts optional transaction fields. Use dated rows and signed amounts for meaningful analytics (income positive, expenses negative), for example:

```csv
date,description,merchant,amount,category
2026-10-01,Monthly salary,Employer,50000.00,Income
2026-10-02,Groceries,Local shop,-1500.00,Groceries
```

## Validation

```bash
python -m pytest backend -q
python -m pytest backend/test_obligation_reconciliation.py -q
python -m compileall -q backend/app
python scripts/generate_frontend_contracts.py --check
git diff --check
```

From `frontend/`, run:

```bash
npm run typecheck
npm run lint
npm test
npm run build
npm run test:browser
```

Browser tests require a Playwright-supported browser; the AI-15B local run used installed Chrome via `$env:PLAYWRIGHT_CHANNEL='chrome'` in PowerShell. See [frontend setup and verification](frontend/README.md).

AI-15B validation recorded **418 backend tests passed, 1 opt-in live test skipped; 41 frontend tests passed; and 21 browser tests passed, 5 existing duplicate viewport cases skipped**. A final focused desktop/mobile browser rerun passed both scenarios. Migration roundtrip, compile, generated contracts, frontend typecheck/lint/build, and whitespace checks passed. These are recorded milestone results, not a guarantee about future changes.

Tests cover calculation services, categorization, finance evidence and routing, schemas, repository/database round trips, user isolation, concurrent allocation integrity, and API behavior. AI tests mock provider failures and malformed output; live-provider smoke checks require explicit opt-in. Passing local tests does not establish production readiness.

## Author

**Shahriar Zeem** — Backend Developer | ML Enthusiast

- [GitHub](https://github.com/mutassimalzeem)
- [Portfolio](https://mutassimalzeem.vercel.app/)
- [LinkedIn](https://www.linkedin.com/in/mutassimalzeem/)

## Frontend

The React + TypeScript application is in [`frontend/`](frontend/README.md), with overview, cashflow, transactions, plans, insights, Ask and settings screens connected to the existing API. Start the backend, then run `npm ci` and `npm run dev` from `frontend/`. Cashflow includes AI-15B candidate review, allocation progress, and explicit confirm/remove controls in both languages. See the [frontend refinement audit](docs/frontend-refinement.md) and [AI-15B report](docs/ai-15b-obligation-reconciliation.md) for API contracts, verification results, and limitations.
