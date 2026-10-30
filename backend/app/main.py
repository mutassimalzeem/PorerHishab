from fastapi import FastAPI, HTTPException, File, UploadFile, Request, Depends, Form, Query
import pandas as pd
import io
from app.core.database import get_db
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
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session


from app.api.forecast import router as forecast_router
from app.api.planner import router as planner_router
from app.api.chat import router as chat_router
from app.api.coach import router as coach_router
from app.api.intelligence import router as intelligence_router
from app.api.scheduled_cashflow import router as scheduled_cashflow_router
from app.api.spending_decision import router as spending_decision_router

from app.services.transaction_service import save_transactions
from app.repositories.transaction_repository import (
    list_transactions,
    search_transactions,
)

app = FastAPI(
    title="PorerHishab API",
    description=(
        "PorerHishab (পরের হিসাব) provides transaction ingestion and categorization, "
        "financial analytics, finance Q&A, budget and cashflow forecasting, "
        "savings planning, and AI guidance grounded in financial data."
    ),
)

app.include_router(insights_router)
app.include_router(transactions_router)
app.include_router(chat_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(forecast_router)
app.include_router(planner_router)
app.include_router(spending_decision_router)
app.include_router(scheduled_cashflow_router)
app.include_router(coach_router)

app.include_router(intelligence_router)

class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str


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


class CSVUploadResponse(BaseModel):
    filename: str
    records: int
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


        access_token = create_access_token({"sub": user.email, "user_id": user.id})
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
        if not user or not user.hashed_password:
            record_failed_attempt(key)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not verify_password(payload.password, user.hashed_password):
            record_failed_attempt(key)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access = create_access_token({"sub": user.email, "user_id": user.id})
        refresh = create_refresh_token({"sub": user.email, "user_id": user.id})
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
def refresh_token(refresh_token: str = Form(...)):
    try:
        data = decode_refresh_token(refresh_token)
        user_id = data.get("user_id")
        email = data.get("sub")
        new_access = create_access_token({"sub": email, "user_id": user_id})
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



@app.post("/upload-csv", response_model=CSVUploadResponse)
async def upload_csv(file: UploadFile = File(...), current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    try:
        raw = await file.read()

        # 1) Read as "object" to avoid Pandas extension dtypes that carry <NA>
        df = pd.read_csv(
            io.BytesIO(raw),
            dtype=object,           # <- objects, not StringDtype
            keep_default_na=True,   # OK to parse NA/NaN initially
            na_filter=True
        )

        # 2) Convert ALL NA-ish to None, and ensure python objects
        df = df.astype(object).where(pd.notnull(df), None)

        # 3) Basic checks & coercions
        if 'amount' not in df.columns:
            raise HTTPException(status_code=400, detail="CSV must include an 'amount' column")

        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)

        # (optional) normalize strings to stripped python str
        for col in ["description", "merchant", "category"]:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

        # 4) Save per-user
        save_transactions(df, user_id=current.id)

        # 5) Summary (safe—no pd.NA remains)
        total_income = float(df[df["amount"] > 0]["amount"].sum() or 0.0)
        total_expenses = float(df[df["amount"] < 0]["amount"].sum() or 0.0)
        balance = total_income + total_expenses

        preview = df.head(10).to_dict(orient="records")
        return {
            "filename": file.filename,
            "records": int(len(df)),
            "total_income": total_income,
            "total_expenses": total_expenses,
            "balance": balance,
            "preview": preview
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {e}")


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
    return {"id": current.id, "email": current.email, "full_name": current.full_name}


@app.get("/transactions/me")
def my_transactions(limit: int = 100, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = list_transactions(db = db, limit = limit, user_id= current.id)

    return {"count": len(rows), "items": rows}