from fastapi import FastAPI, HTTPException, File, UploadFile, Request, Depends, Form
import pandas as pd
import io
from db import init_db, SessionLocal
from db_store import save_dataframe, list_transactions, clear_transactions
from auth import get_password_hash, create_access_token, create_refresh_token, rate_limit_guard, record_failed_attempt
from models import User
from pydantic import BaseModel, EmailStr
from typing import Optional
from auth import verify_password, decode_access_token
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


init_db()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str

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
def login(request: Request, payload: LoginIn):
    db = SessionLocal()
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



security = HTTPBearer()

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> User:
    token = creds.credentials

    try:
        data = decode_access_token(token)

    except Exception:
        raise  HTTPException(status_code= 401, detail = 'Invalid or expired token')
    
    user_id = data.get("user_id")
    email = data.get("sub")

    if user_id is None or not email:
        raise HTTPException(status_code= 401, detail = 'Invalid token payload')
    
    db = SessionLocal()

    try:
        user = db.query(User).filter(User.id == user_id, User.email == email).first()
        if not user:
            raise HTTPException(status_code= 401, detail = 'User not found')
        
        return user
    finally:
        db.close()


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
def get_summary(current: User = Depends(get_current_user)):
    try:
        transactions = list_transactions(limit=10000, user_id= current.id)  # Get all transactions
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
async def upload_csv(file: UploadFile = File(...), current: User = Depends(get_current_user)):

    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")
    
    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        
        if 'amount' not in df.columns:
            raise HTTPException(status_code=400, detail="CSV must include an 'amount' column")
        
        df["amount"] = pd.to_numeric(df["amount"], errors='coerce').fillna(0.0)
        
        # Save to database
        save_dataframe(df, user_id= current.id)
        
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
    

@app.get("/me")
def read_me(current: User = Depends(get_current_user)):
    return {"id": current.id, "email": current.email, "full_name": current.full_name}


@app.get("/transactions/me")
def my_transactions(limit: int = 100, current: User = Depends(get_current_user)):
    rows = list_transactions(limit = limit, user_id= current.id)

    return {"count": len(rows), "items": rows}