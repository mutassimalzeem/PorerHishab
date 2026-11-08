from decimal import Decimal
from fastapi import FastAPI, HTTPException, File, UploadFile, Request, Depends, Form, Query
import pandas as pd
import io
from app.core.database import get_db
from app.core.config import settings
from app.api.health import router as health_router
from app.api.email_verification import router as email_verification_router
from app.api.auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    get_password_hash,
    rate_limit_guard,
    record_failed_attempt,
    verify_password,
)
from app.api.insights import router as insights_router
from app.api.transactions import router as transactions_router
from app.core.dependencies import get_current_user
from app.models.user import User
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool


from app.api.coaching import router as coaching_router
from app.api.action_outcome import router as action_outcome_router
from app.api.timeline import router as timeline_router
from app.api.runway import router as runway_router
from app.api.financial_health import router as financial_health_router
from app.api.goal_planning import router as goal_planning_router
from app.api.scenarios import router as scenarios_router
from app.api.forecast import router as forecast_router
from app.api.planner import router as planner_router
from app.api.chat import router as chat_router
from app.api.coach import router as coach_router
from app.api.intelligence import router as intelligence_router
from app.api.obligation_reconciliation import router as obligation_reconciliation_router
from app.api.scheduled_cashflow import router as scheduled_cashflow_router
from app.api.spending_decision import router as spending_decision_router
from app.api.accounts import router as accounts_router
from app.api.account_reconcilliation import router as account_reconcilliation_router
from app.api.financial_alerts import router as alerts_router
from app.api.notification_preferences import router as notification_preferences_router
from app.api.financial_coach import router as financial_coach_router
from app.api.financial_review import router as financial_review_router

from app.services.transaction_service import save_transactions
from app.repositories.transaction_repository import (
    list_transactions,
    search_transactions,
)


from app.middleware.request_size_limit import RequestBodyLimitMiddleware



app = FastAPI(
    title="PorerHishab API",
    description=(
        "PorerHishab (পরের হিসাব) provides transaction ingestion and categorization, "
        "financial analytics, finance Q&A, budget and cashflow forecasting, "
        "savings planning, and AI guidance grounded in financial data."
    ),
)

app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes= 5 * 1024 * 1024)

app.include_router(health_router)
app.include_router(email_verification_router)
app.include_router(insights_router)
app.include_router(transactions_router)
app.include_router(chat_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(coaching_router)
app.include_router(action_outcome_router)
app.include_router(timeline_router)
app.include_router(runway_router)
app.include_router(financial_health_router)
app.include_router(forecast_router)
app.include_router(planner_router)
app.include_router(spending_decision_router)
app.include_router(obligation_reconciliation_router)
app.include_router(scheduled_cashflow_router)
app.include_router(goal_planning_router)
app.include_router(scenarios_router)
app.include_router(coach_router)

app.include_router(intelligence_router)
app.include_router(accounts_router)
app.include_router(account_reconcilliation_router)
app.include_router(alerts_router)
app.include_router(notification_preferences_router)
app.include_router(financial_coach_router)
app.include_router(financial_review_router)

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=1024)
    full_name: Optional[str] = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class RegisterTokenResponse(BaseModel):
    access_token: str
    token_type: str


class LoginTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str


class CSVRowError(BaseModel):
    row: int
    field: str
    message: str


class CSVUploadResponse(BaseModel):
    filename: str
    records: int
    rows_received: int
    rows_persisted: int
    rows_rejected: int
    rows_skipped: int
    errors: List[CSVRowError]
    total_income: float
    total_expenses: float
    balance: float
    preview: List[dict[str, Any]]


@app.post("/register", response_model=RegisterTokenResponse)
def register(payload: RegisterIn,
    db: Session = Depends(get_db)):

    try:
        existing = db.query(User).filter(User.email == payload.email).first()
        if existing:
            raise HTTPException(status_code= 400, detail= 'Email already registered')

        hashed = get_password_hash(payload.password)
        user = User(email = str(payload.email), hashed_password = hashed, full_name = payload.full_name)
        db.add(user)
        db.commit()
        db.refresh(user)


        access_token = create_access_token({"sub": user.email, "user_id": user.id, "ver": user.token_version})
        return {'access_token': access_token, "token_type": 'bearer'}

    finally:
        db.close()


@app.post("/login", response_model=LoginTokenResponse)
def login(request: Request, payload: LoginIn, db: Session = Depends(get_db)):
    try:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{payload.email}"
        rate_limit_guard(key)

        user = db.query(User).filter(User.email == str(payload.email)).first()

        if not user or not verify_password(payload.password, user.hashed_password):
            record_failed_attempt(key)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access = create_access_token({"sub": user.email, "user_id": user.id, "ver": user.token_version})
        refresh = create_refresh_token({"sub": user.email, "user_id": user.id, "ver": user.token_version})
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}
    finally:
        db.close()


@app.get("/search")
def search(
    q: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    category: Optional[List[str]] = Query(None, description= "Filter by categories; e.g. ?category=Food&category=Utilities"),
    limit: int = 100,
    offset: int = 0,
    sort: str = "desc",
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if sort not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="sort must be 'asc' or 'desc'")

    items = search_transactions(db = db,
        user_id=current.id,
        q=q,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        max_amount=max_amount,
        categories=category,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    return {"count": len(items), "items": items}



@app.post("/refresh", response_model=RefreshTokenResponse)
def refresh_token(refresh_token: str = Form(...), db: Session = Depends(get_db)):
    try:
        data = decode_refresh_token(refresh_token)
        user_id = data.get("user_id")
        email = data.get("sub")
        user = db.query(User).filter(User.id == user_id, User.email == email).first()
        if user is None or data.get("ver", 0) != user.token_version:
            raise HTTPException(401, "Invalid or expired refresh token")
        new_access = create_access_token({"sub": email, "user_id": user_id, "ver": user.token_version})
        return {"access_token": new_access, "token_type": "bearer"}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")


@app.get("/")
def read_root():
    return {"message": "PorerHishab is alive!"}


@app.get("/summary")
def get_summary(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        transactions = list_transactions(db = db, limit=10000, user_id= current.id)  # Get all transactions
        df = pd.DataFrame(transactions)

        if df.empty:
            return {
                "total_income": 0.0,
                "total_expenses": 0.0,
                "balance": 0.0
            }

        total_income = float(df[df["amount"] > 0]["amount"].sum() or 0.0)
        total_expenses = float(df[df["amount"] < 0]["amount"].sum() or 0.0)
        balance = float(total_income + total_expenses)

        return {
            "total_income": total_income,
            "total_expenses": total_expenses,
            "balance": balance
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")



MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_CSV_ROWS = 10_000

@app.post("/upload-csv", response_model=CSVUploadResponse)
async def upload_csv(file: UploadFile = File(...), current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    try:
        raw = await file.read(MAX_CSV_BYTES + 1)

        if len(raw) > MAX_CSV_BYTES:
            raise HTTPException(status_code= 413, detail = "CSV file exceeds the 5 MiB upload limit.")

        # 1) Read as "object" to avoid Pandas extension dtypes that carry <NA>
        df = await run_in_threadpool(
            pd.read_csv,
            io.BytesIO(raw),
            dtype=object,
            keep_default_na=True,
            na_filter=True,
            nrows=MAX_CSV_ROWS + 1)

        if len(df) > MAX_CSV_ROWS:
            raise HTTPException(
                status_code=413,
                detail=f"CSV exceeds the {MAX_CSV_ROWS}-row limit.",
            )

        # 2) Convert ALL NA-ish to None, and ensure python objects
        df = df.astype(object).where(pd.notnull(df), None)

        # 3) Basic checks & coercions
        if 'amount' not in df.columns:
            raise HTTPException(status_code=400, detail="CSV must include an 'amount' column")

        # (optional) normalize strings to stripped python str
        for col in ["description", "merchant", "category"]:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

        # Persistence returns its actual committed/refreshed records. Counts,
        # preview and Decimal totals are all derived from that same result.
        result = await run_in_threadpool(save_transactions, df, current.id, detailed = True)

        amounts = [row.amount for row in result.transactions]
        total_income = sum((value for value in amounts if value > 0), Decimal("0.00"))
        total_expenses = sum((value for value in amounts if value < 0), Decimal("0.00"))
        preview_fields = ("date", "amount", "description", "merchant", "category", "normalized_merchant")
        return {
            "filename": file.filename,
            "records": result.rows_persisted,
            "rows_received": result.rows_received,
            "rows_persisted": result.rows_persisted,
            "rows_rejected": result.rows_rejected,
            "rows_skipped": 0,
            "errors": result.errors,
            "total_income": float(total_income),
            "total_expenses": float(total_expenses),
            "balance": float(total_income + total_expenses),
            "preview": [{field: getattr(row, field) for field in preview_fields}
                        for row in result.transactions[:10]],
        }
    except HTTPException:
        raise
    except (ValueError, pd.errors.ParserError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {e}")
    except Exception:
        raise HTTPException(status_code=500, detail="CSV persistence failed")


@app.get("/categories/summary")
def categories_summary(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        rows = list_transactions(db = db, limit=100000, user_id=current.id)
        df = pd.DataFrame(rows)
        if df.empty:
            return {
                "income_by_category": {},
                "expenses_by_category": {},
                "net_by_category": {},
                "grand_totals": {"income": 0.0, "expenses": 0.0, "net": 0.0}
            }

        # Ensure types
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        df["category"] = df["category"].fillna("Other").astype(str)

        # Income (amount > 0)
        inc = df[df["amount"] > 0].groupby("category", dropna=False)["amount"].sum()
        income_by_category = {k: float(v) for k, v in inc.to_dict().items()}

        # Expenses (amount < 0)
        exp = df[df["amount"] < 0].groupby("category", dropna=False)["amount"].sum()
        expenses_by_category = {k: float(v) for k, v in exp.to_dict().items()}

        # Net by category (sum of all amounts)
        net = df.groupby("category", dropna=False)["amount"].sum()
        net_by_category = {k: float(v) for k, v in net.to_dict().items()}

        grand_income = float((df[df["amount"] > 0]["amount"].sum()) or 0.0)
        grand_expenses = float((df[df["amount"] < 0]["amount"].sum()) or 0.0)
        grand_net = float(grand_income + grand_expenses)

        return {
            "income_by_category": income_by_category,
            "expenses_by_category": expenses_by_category,
            "net_by_category": net_by_category,
            "grand_totals": {
                "income": grand_income,
                "expenses": grand_expenses,
                "net": grand_net
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summary failed: {str(e)}")


@app.get("/me")
def read_me(current: User = Depends(get_current_user)):
    return {"id": current.id, "email": current.email, "full_name": current.full_name, "email_verified": current.email_verified}


@app.get("/transactions/me")
def my_transactions(limit: int = 100, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = list_transactions(db = db, limit = limit, user_id= current.id)

    return {"count": len(rows), "items": rows}
