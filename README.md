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

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- JWT Authentication
- Pydantic
- Uvicorn

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

## Project Architecture

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

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Create a new user account |
| `POST` | `/auth/login` | Login and receive access token |
| `GET` | `/users/me` | Get current user profile |
| `POST` | `/transactions/upload-csv` | Upload transaction CSV |
| `GET` | `/transactions/me` | Get user transactions |
| `GET` | `/summary` | Get spending summary |
| `GET` | `/insights/monthly` | Get monthly spending insights |
| `POST` | `/chat/ask` | Ask finance questions |
| `GET` | `/forecast/budget` | Get budget forecast |
| `GET` | `/planner/savings` | Get saving recommendations |

---

## Environment Variables

Create a `.env` file inside the backend directory.

```env
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/zyra

SECRET_KEY=your_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

OPENAI_API_KEY=your_openai_api_key
EMBEDDING_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini

USE_HF=0
HF_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

For local-only embedding experiments, you can use Hugging Face embeddings instead of OpenAI embeddings.

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
python -m venv venv
```

Activate the environment:

```bash
# Windows
venv\Scripts\activate
```

```bash
# macOS/Linux
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the backend:

```bash
uvicorn app.main:app --reload
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

### 4. Setup Frontend

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

## Current Status

- [x] Project idea and architecture
- [x] Backend planning
- [x] Authentication flow
- [x] Transaction ingestion design
- [x] AI/RAG planning
- [ ] Full frontend dashboard
- [ ] Advanced transaction categorization
- [ ] Budget forecasting improvements
- [ ] Goal-based savings planner
- [ ] Production deployment

---

## Future Improvements

- Bank account integration
- More advanced forecasting models
- Spending anomaly detection
- Recurring subscription detection
- Multi-account support
- Exportable finance reports
- Monthly email summaries
- Mobile-friendly UI
- Voice-based finance assistant
- Better financial goal tracking
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
