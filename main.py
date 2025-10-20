from fastapi import FastAPI, HTTPException, File, UploadFile, APIRouter, Request
import pandas as pd
import io
from db import init_db, SessionLocal
from db_store import save_dataframe, list_transactions, clear_transactions
from auth import get_password_hash, create_access_token, create_refresh_token, rate_limit_guard, record_failed_attempt
from models import User
from pydantic import BaseModel, EmailStr
from typing import Optional
from auth import verify_password


init_db()
app = FastAPI()

class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

db_path = 'transactions.db'

CREATE_SQL = """CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT)"""


@app.post("/register")
def register(payload: RegisterIn):
    db= SessionLocal()

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

@app.post("/login")
def login(request: Request, email: str, password: str):
    db = SessionLocal()

    try:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{email}"
        rate_limit_guard(key)

        user = db.query(User).filter(User.email == email).first()

        if not user or not user.hashed_password:
            record_failed_attempt(key)
            raise HTTPException(status_code=400, detail= "Invalid Credentials")

        if not verify_password(password, user.hashed_password):
            record_failed_attempt(key)
            raise HTTPException(status_code=400, detail= "Invalid Credentials")
        
        access = create_access_token({'sub': user.email, 'user_id': user.id})
        refresh = create_refresh_token({'sub': user.email, 'user_id': user.id})
        return {'access_token': access, 'refresh_token': refresh, 'token_type': 'bearer'}
    
    finally:
        db.close()

from fastapi import Form

@app.post("/refresh")
def refresh_token(refresh_token: str = Form(...)):
    from auth import decode_refresh_token
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
    return {"message": "Smart Finance Coach is alive!"}


@app.get("/summary")
def get_summary():
    try:
        transactions = list_transactions(limit=10000)  # Get all transactions
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



@app.post('/upload-csv')
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")
    
    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        
        if 'amount' not in df.columns:
            raise HTTPException(status_code=400, detail="CSV must include an 'amount' column")
        
        df["amount"] = pd.to_numeric(df["amount"], errors='coerce').fillna(0.0)
        
        # Save to database
        save_dataframe(df)
        
        # Calculate summary from the dataframe we just processed
        total_income = float(df[df["amount"] > 0]["amount"].sum())
        total_expenses = float(df[df["amount"] < 0]["amount"].sum())
        balance = total_income + total_expenses
        
        preview = df.head(10).to_dict(orient="records")
        
        return {
            'filename': file.filename,
            'records': len(df),
            "total_income": total_income,
            "total_expenses": total_expenses,
            "balance": balance,
            'preview': preview
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")