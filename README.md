# পরের হিসাব — PorerHishab

**আজকের খরচ, আগামীর পরিকল্পনা।**

PorerHishab is a Bangladesh-first personal finance coach that helps users understand their current financial position and work toward knowing what they can safely spend after accounting for upcoming obligations and expected income.

The product direction is a Bangla-first AI financial coach: **Know what you can spend after accounting for what comes next.** Bangla-first interaction and obligation-aware safe-to-spend decisions are goals; the current repository implements the backend capabilities listed below.

## Implementation status

### Implemented

- JWT access/refresh authentication and user-scoped transaction access.
- CSV transaction ingestion, transaction creation/listing, filtering, search, and category corrections.
- Categorization using merchant preferences, deterministic rules, and validated LLM fallback.
- Financial analytics: income, expenses, savings rate, monthly and month-over-month breakdowns, categories, merchants, recurring charges, cashflow history, and budget baselines.
- Finance Q&A using structured financial evidence and transaction retrieval, with LLM-generated answers.
- Budget forecasting from historical and recent monthly spending, with category forecasts.
- Savings goal planning and AI-generated savings actions grounded in the plan.
- AI-generated financial insights grounded in analytics.
- PostgreSQL models, Alembic migrations, and backend unit/API/integration tests.

AI features require a configured compatible provider and credentials. Their presence in the source does not imply production readiness or guaranteed financial outcomes.

### In progress

- Cashflow forecasting: the current working tree includes a forecast service, response schema, `/forecast/cashflow` route, and calculation tests. This work is uncommitted and under development.
- Keeping documentation and packaging aligned with the PorerHishab brand.

### Planned

- Frontend dashboard and Bangla/Roman Bangla interaction. No frontend source exists in this repository yet.
- MFS SMS and bank PDF ingestion, banking integrations, and automatic syncing.
- Explicit upcoming-bill/income scheduling and safe-to-spend decisions.
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

These are product goals, not claims that current forecasts model scheduled bills or guarantee spending safety.

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

Backend tools include FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Alembic, pandas, Uvicorn, LangChain, and Chroma. AI/RAG modules also require their provider and LangChain dependencies in the environment; the existing requirements file is not a complete reproducible AI environment specification.

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
| GET | `/forecast/cashflow` | In-progress cashflow projection |
| POST | `/planner/savings` | Savings goal plan |
| POST | `/planner/savings/coach` | Plan plus AI guidance |

See `/docs` for current request parameters and response schemas. Existing API paths are preserved by the rebrand.

## Local development

The repository root is the canonical working directory.

The intended repository name is **PorerHishab**. The owner must rename the existing GitHub repository before relying on this clone URL:

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

The API runs at `http://localhost:8000`, with documentation at `http://localhost:8000/docs`. Database-backed tests require PostgreSQL. Some existing RAG smoke tests call an external embedding provider and write vector data; they require configured credentials and network access.

`python scripts/check_uvicorn.py` provides a startup smoke check. From `backend/`, the Alembic shim and pytest bootstrap also support local commands, but the repository root remains the recommended starting point.

## Storage compatibility

The rebrand changes display names and package metadata, not persistence identifiers:

- PostgreSQL database and role: `zyra`.
- Existing Compose container: `zyra-db`; service: `db`.
- Existing Compose volume key: `zyra_postgres_data`.
- Existing Chroma collection default: `zyra_transactions`, stored under `data/chroma`.

These are **legacy storage identifiers retained for compatibility**. Keep the current checkout directory and Compose project identity when using existing local volumes: a different directory/project name can select a different Compose-prefixed volume even if the volume key is unchanged.

Tables remain `users`, `accounts`, `transactions`, `transaction_category_corrections`, and `merchant_category_preferences`. No Alembic filenames, revisions, or database schema changes are required.

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
python -m pytest backend/test_cashflow_forecast.py -q
git diff --check
```

Tests cover calculation services, categorization, finance evidence and routing, schemas, repository/database round trips, user isolation, and API behavior. AI tests include mocked checks and live-provider smoke checks; passing local tests does not establish production readiness.

## Author

**Shahriar Zeem** — Backend Developer | ML Enthusiast

- [GitHub](https://github.com/mutassimalzeem)
- [Portfolio](https://mutassimalzeem.vercel.app/)
- [LinkedIn](https://www.linkedin.com/in/mutassimalzeem/)
