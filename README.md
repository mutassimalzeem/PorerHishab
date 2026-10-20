# Zyra — Smart Personal Finance Coach

<p align="center">
  <img src="https://img.shields.io/badge/Python-Backend-blue?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/FastAPI-API-009688?style=for-the-badge&logo=fastapi" />
  <img src="https://img.shields.io/badge/PostgreSQL-Database-336791?style=for-the-badge&logo=postgresql" />
  <img src="https://img.shields.io/badge/LangChain-AI%20Workflow-green?style=for-the-badge" />
  <img src="https://img.shields.io/badge/RAG-Finance%20Q%26A-purple?style=for-the-badge" />
</p>

<p align="center">
  <b>An AI-powered personal finance coach that helps users understand spending, ask natural-language finance questions, forecast budgets, and receive personalized savings recommendations.</b>
</p>

> 🇧🇩 **Bangladesh-First Update (Oct 2026 audit):** Zyra is now **Bangladesh-tailored — bKash / Nagad / Rocket / Upay + Bank BEFTN/NPSB + DPS/FDR**. The full market audit, premium feature vault (Taka Sesh Date, WhatsApp Coach, NBR & Household OS) and 9-month roadmap for 2027 lives in **[FEATURES.md](./FEATURES.md)**. Global Plaid → **MFS SMS Parser + Bank PDF OCR**.

---

## Overview

**Zyra** is a smart personal finance coach built with a production-minded full-stack architecture.

The project allows users to upload transaction data, analyze spending behavior, ask questions about their finances in natural language, and receive personalized budgeting and saving suggestions.

The goal is not just to build another finance dashboard. Zyra is designed as an AI-powered financial assistant where backend engineering, data processing, retrieval-augmented generation, and practical financial insights work together.

---

## Why I Built This

Most people track expenses, but they still struggle to answer simple questions like:

- Where is my money going every month?
- Which category is quietly draining my budget?
- How much can I realistically save this month?
- Am I overspending compared to my previous months?
- What small changes can improve my financial habits?

Zyra tries to solve that by combining transaction analysis with AI-assisted financial reasoning.

Instead of only showing charts, Zyra helps users understand their financial behavior in plain language.

---

## Core Features

### Transaction Upload & Ingestion

Users can upload transaction data through CSV files.

The backend processes the uploaded file, validates required fields, cleans messy values, and stores transactions in the database.

Planned production upgrade:

- Bank account connection using services like Plaid or similar APIs
- Automatic transaction syncing
- Background ingestion jobs

---

### Transaction Categorization

Zyra categorizes transactions using a combination of:

- Rule-based matching
- Merchant name patterns
- Keyword-based category detection
- LLM fallback for uncertain transactions

This makes the system practical for real-world messy transaction data where merchant names are not always clean.

---

### Natural Language Finance Q&A

Users can ask questions such as:

```txt
How much did I spend on food last month?
```

```txt
Which category increased the most compared to the previous month?
```

```txt
What are my top unnecessary expenses?
```

```txt
Can I save 5000 BDT this month?
```

The system answers using the user's own transaction history, not generic finance advice.

---

### RAG-Based Financial Search

Zyra uses retrieval-augmented generation to ground AI answers in the user's personal transaction data.

Basic flow:

```txt
User Question
     ↓
Query Understanding
     ↓
Relevant Transaction Retrieval
     ↓
LLM Reasoning
     ↓
Grounded Financial Answer
```

This makes AI responses more useful, personalized, and connected to actual spending behavior.

---

### Budget Forecasting

Zyra includes simple forecasting logic to estimate upcoming spending patterns based on historical transaction data.

The first version focuses on beginner-friendly forecasting methods such as:

- Monthly spending averages
- Category-wise trend analysis
- Recent spending velocity
- Simple time-series forecasting

Future versions can include more advanced models.

---

### Personalized Saving Suggestions

Zyra recommends practical saving actions based on spending behavior.

Example:

```txt
You spent 18% more on food this month compared to last month.
Reducing food delivery by 2 orders per week could save around 1200–1800 BDT monthly.
```

The focus is on realistic, behavior-based suggestions instead of generic advice.

---

## Tech Stack

### Backend

- Python + FastAPI (`backend/app/main.py` — live: auth, CSV upload, search, summaries)
- SQLAlchemy 2.0 (typed `Mapped` models) + Alembic migrations (`alembic/versions/`)
- PostgreSQL 16 via Docker (`docker-compose.yml` → `zyra-db`)
- JWT access + refresh (peppered bcrypt, per-IP rate-limit) — see `backend/app/api/auth.py`
- Pydantic v2 + pydantic-settings (`.env` → `DATABASE_URL`)
- Uvicorn

> Note: `backend/app/main.py` is the current runnable entrypoint. The sculpted
> `backend/app/api/*`, `schemas/*`, `services/*` modules from `architecture.md`
> are placeholders (empty stubs) reserved for the v2 router split.

### AI / ML

- LangChain
- OpenAI API or Hugging Face models
- FAISS / Chroma for vector search
- Embeddings for transaction retrieval
- Rule-based + LLM-assisted categorization

### Data Processing

- Pandas
- CSV parsing
- Transaction cleaning
- Category mapping
- Monthly aggregation

### Frontend

- React
- Vite
- Tailwind CSS
- Dashboard UI
- Charts and analytics views

### DevOps / Tooling

- Docker
- Docker Compose
- `.env` based configuration
- PostgreSQL container setup
- Local development workflow

---

## Data Model (v2 — `feature/zyra-v2`)

Live on this branch via `alembic revisions b348fd279e16 → c2d11a3f4b5c`
(`dates` → `date` rename):

```txt
users (id, email unique, hashed_password, full_name, created_at, updated_at)
  ├── accounts (id, user_id → users.id CASCADE, name, source [bkash/nagad/bank/cash],
  │              account_type [cash/mobile_wallet/bank], currency default BDT,
  │              current_balance NUMERIC(14,2), created_at)
  └── transactions (id, user_id → users.id CASCADE, account_id → accounts.id SET NULL,
                    trx_id, date DATE, description, merchant, normalized_merchant,
                    amount NUMERIC(14,2), fee NUMERIC(14,2) default 0, balance,
                    transaction_type, category, subcategory,
                    source [manual/csv/sms/pdf], is_recurring bool,
                    raw_data JSONB, created_at,
                    UNIQUE(user_id, trx_id))
```

- Money-safe: `NUMERIC(14,2)` for `amount/fee/balance` (never float).
- Bangladesh-ready: `fee` + `balance` + `trx_id` columns capture
  `Cash Out Tk1,500 to 017XX TrxID 9AX Fee Tk27.50` SMS shapes (parser lands in M1-2 per `FEATURES.md`).
- Verified by `backend/test_database.py::test_database_relationships`
  (user → bKash account → Foodpanda transaction).

---

## Project Architecture (target — see `architecture.md`)

> Current runnable code lives in `backend/app/main.py`. The tree below is the
> v2 target; `api/*`, `schemas/*`, `services/*` stubs are empty and tracked
> for the upcoming router split.

```txt
Zyra/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── transactions.py
│   │   │   ├── insights.py
│   │   │   └── chat.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── database.py
│   │   │
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   └── transaction.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── user.py
│   │   │   └── transaction.py
│   │   │
│   │   ├── services/
│   │   │   ├── ingestion.py
│   │   │   ├── categorization.py
│   │   │   ├── forecasting.py
│   │   │   ├── savings_planner.py
│   │   │   └── rag_service.py
│   │   │
│   │   └── main.py
│   │
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/
│   │   └── App.jsx
│   │
│   ├── package.json
│   └── vite.config.js
│
├── docs/
│   ├── architecture.md
│   ├── api-design.md
│   └── roadmap.md
│
├── docker-compose.yml
├── .env.example
├── README.md
└── LICENSE
```

---

## System Design Overview

```txt
                ┌────────────────────┐
                │      Frontend       │
                │   React + Vite      │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │      FastAPI        │
                │   Backend Server    │
                └─────────┬──────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ PostgreSQL   │   │ Vector Store │   │ AI Services  │
│ Transactions │   │ FAISS/Chroma │   │ LangChain    │
└──────────────┘   └──────────────┘   └──────────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
                ┌────────────────────┐
                │ Personalized        │
                │ Finance Insights    │
                └────────────────────┘
```

---

## Main User Flow

```txt
1. User creates an account
2. User uploads transaction CSV
3. Backend cleans and stores transactions
4. System categorizes transactions
5. Transactions are embedded for retrieval
6. User views dashboard insights
7. User asks finance questions
8. RAG pipeline retrieves relevant data
9. AI generates grounded answers
10. System recommends saving actions
```

---

## Example Questions Zyra Can Answer

```txt
How much did I spend this month?
```

```txt
What are my top 5 expense categories?
```

```txt
Did my food spending increase compared to last month?
```

```txt
Which transactions look unnecessary?
```

```txt
How much can I save if I reduce entertainment spending?
```

```txt
Create a savings plan for the next 3 months.
```

---

## API Endpoints (live on this branch)

| Method | Endpoint | Description | Status |
|---|---|---|---|
| `POST` | `/register` | Create user, return access token | ✅ live in `main.py` |
| `POST` | `/login` | Login (rate-limited) → access + refresh | ✅ live |
| `POST` | `/refresh` | Exchange refresh token for access token | ✅ live |
| `GET` | `/me` | Current user profile | ✅ live |
| `POST` | `/upload-csv` | Upload CSV (requires `amount`; optional `description/merchant/category`) | ✅ live |
| `GET` | `/transactions/me?limit=100` | List own transactions | ✅ live |
| `GET` | `/search?q=&category=&limit=` | Full-text + category + amount + date search | ✅ live |
| `GET` | `/summary` | Income / expenses / balance totals | ✅ live |
| `GET` | `/categories/summary` | Income / expenses / net per category | ✅ live |
| `POST` | `/chat/ask` | RAG finance Q&A | 🔜 stub per `architecture.md` |
| `GET` | `/forecast/budget` | Taka Sesh Date predictor | 🔜 per `FEATURES.md M3-5` |
| `GET` | `/planner/savings` | Fee Killer + saving plan | 🔜 per `FEATURES.md M3-5` |

---

## Environment Variables

Create a `.env` file at repo root (loaded by `backend/app/core/config.py`).

```env
DATABASE_URL=postgresql+psycopg2://zyra:zyra_password@localhost:5432/zyra
SECRET_KEY=change-me-in-prod
REFRESH_SECRET_KEY=change-me-in-prod-refresh
PEPPER=
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=14
RATE_LIMIT_WINDOW_SECONDS=300
RATE_LIMIT_MAX_ATTEMPTS=5
```

> `DATABASE_URL` must use `+psycopg2` (sync) — `create_engine(...)` in
> `core/database.py` is sync. See `.env.example`. OpenAI / HF embedding keys
> arrive with the RAG service (M3-5).

---

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/mutassimalzeem/Zyra.git
cd Zyra
```

---

### 2. Start PostgreSQL with Docker

```bash
docker compose up -d
```

Or manually run PostgreSQL:

```bash
docker run --name zyra-postgres \
  -e POSTGRES_USER=zyra \
  -e POSTGRES_PASSWORD=zyra \
  -e POSTGRES_DB=zyra \
  -p 5432:5432 \
  -d postgres:16
```

For Windows PowerShell, use this one-line version:

```powershell
docker run --name zyra-postgres -e POSTGRES_USER=zyra -e POSTGRES_PASSWORD=zyra -e POSTGRES_DB=zyra -p 5432:5432 -d postgres:16
```

---

### 3. Setup Backend

```bash
cd backend
python -m venv .venv
```

Activate the environment:

```bash
# Windows
.venv\Scripts\activate
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy env + migrate + run (from repo root):

```bash
cp .env.example .env
alembic upgrade head
pytest backend/test_database.py -v
uvicorn backend.app.main:app --reload
```

Backend will run at:

```txt
http://localhost:8000
```

API docs:

```txt
http://localhost:8000/docs
```

---

### 4. Setup Frontend (planned)

> No `frontend/` directory on this branch yet — Next.js + PWA lands in M1-2.
> Reserved flow from `architecture.md`:

```bash
cd frontend
npm install
npm run dev
```

Frontend will run at:

```txt
http://localhost:5173
```

---

## CSV Format

The uploaded CSV should contain transaction data.

Recommended columns:

```csv
date,description,amount,type
2026-01-01,Foodpanda Order,450,expense
2026-01-02,Salary,30000,income
2026-01-03,Uber Ride,220,expense
```

Minimum required fields:

| Column | Description |
|---|---|
| `date` | Transaction date |
| `description` | Merchant or transaction description |
| `amount` | Transaction amount |

Optional fields:

| Column | Description |
|---|---|
| `type` | income or expense |
| `category` | food, transport, rent, salary, etc. |
| `account` | bank, card, wallet, cash |

---

## Example AI Response

User question:

```txt
Where did I overspend this month?
```

Zyra response:

```txt
Your food and transport spending increased compared to last month.

Food spending increased by 22%.
Transport spending increased by 14%.

The biggest change came from repeated food delivery transactions.
If you reduce food delivery by 2 orders per week, you could save approximately 1200–1800 BDT per month.
```

---

## What Makes This Project Valuable

This project combines multiple real-world engineering skills:

- Backend API design
- Authentication and user-specific data handling
- Database modeling
- CSV ingestion and data validation
- Financial data analysis
- RAG-based AI question answering
- Forecasting and recommendation logic
- Frontend dashboard development
- Docker-based local development
- Production-minded project structure

Zyra is built as a practical AI product, not just a tutorial project.

---

## Current Status (`feature/zyra-v2` @ Oct 2026)

- [x] Project idea and architecture (`architecture.md`)
- [x] Backend planning + v2 data model (`users` → `accounts` → `transactions`)
- [x] Alembic baseline `b348fd279e16` + rename `c2d11a3f4b5c` (NUMERIC money, `trx_id`, `fee`, `balance`, `raw_data`)
- [x] Authentication flow (JWT access + refresh, peppered bcrypt, rate-limit)
- [x] Transaction ingestion (CSV) + search + category summaries + per-user isolation
- [x] DB relationship test (`backend/test_database.py`)
- [x] Market audit + Bangladesh premium vault → `FEATURES.md`
- [ ] Router split (`main.py` → `api/*` + `schemas/*` + `services/*`)
- [ ] Full frontend dashboard (Next.js + PWA)
- [ ] MFS SMS + Bank PDF ingestion (Bangladesh-first)
- [ ] FinBangla-BERT categorizer + fee/balance model
- [ ] Taka Sesh Date predictor + Fee Killer
- [ ] WhatsApp/Messenger Coach + NBR/DPS OS
- [ ] Production deployment (Postgres + Docker + SSLCommerz)

---

## Premium Roadmap for Bangladesh (2027) — See FEATURES.md

> Full audit + tiered Bangladesh stack: **bKash/Nagad SMS Parser + Bank PDF OCR, Taka Sesh Date predictor, Fee Killer, WhatsApp/Messenger Coach, NBR Wealth OS, Household & Mess OS.**

Tiers: **Free 0 | PRO Tk 2,999/yr | PREMIUM Tk 4,999/yr** via bKash/Nagad/SSLCommerz. See `FEATURES.md §3-7`.

## Future Improvements

- MFS SMS auto-parse (bKash/Nagad/Rocket/Upay) + Bank PDF OCR (BRAC/City/EBL/DBBL/Islami)
- FinBangla-BERT categorizer for Bangla/Roman Bangla + fee split
- Taka Sesh Date cashflow predictor (Eid-aware) + Fee & Subscription Killer
- WhatsApp/Messenger AI Coach + NBR e-TIN + DPS/FDR + CIB health
- Household & Mess shared vault (5 members)
- More advanced forecasting models
- Spending anomaly detection
- Multi-account (MFS + Bank + Cash) support
- Exportable finance reports
- Monthly WhatsApp/email summaries
- Mobile-friendly PWA + Voice assistant
- Deployment with Docker and cloud hosting

---

## Learning Goals

Through this project, I am focusing on:

- Building production-minded backend systems
- Connecting AI with real user data
- Designing practical RAG workflows
- Improving API and database design
- Learning how to turn ML/AI concepts into useful products
- Writing cleaner project documentation
- Building portfolio projects that solve real problems

---

## Suggested GitHub Repository Description

```txt
AI-powered personal finance coach with transaction ingestion, budget insights, RAG-based finance Q&A, forecasting, and personalized savings recommendations.
```

---

## Suggested GitHub Topics

```txt
fastapi
python
postgresql
langchain
rag
personal-finance
finance-ai
openai
machine-learning
react
vite
docker
ai-application
budgeting
```

---

## Author

**Shahriar Zeem**  
Backend Developer | ML Enthusiast | FastAPI, Python, PostgreSQL  
Building AI-powered apps and solving real-world engineering problems.

- GitHub: [mutassimalzeem](https://github.com/mutassimalzeem)
- Portfolio: [mutassimalzeem.vercel.app](https://mutassimalzeem.vercel.app/)
- LinkedIn: [mutassimalzeem](https://www.linkedin.com/in/mutassimalzeem/)

---

## License

This project is open-source and available under the MIT License.

---

## Final Note

Zyra is still evolving.

The long-term goal is to turn it into a complete AI-powered personal finance assistant that can understand transactions, explain spending behavior, forecast budgets, and help users make better money decisions.
