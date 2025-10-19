from fastapi import FastAPI, HTTPException, File, UploadFile
import pandas as pd
import io
from db import init_db
from db_store import save_dataframe, list_transactions, clear_transactions

init_db()
app = FastAPI()
db_path = 'transactions.db'

CREATE_SQL = """CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT)"""
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
                "total_income": 0,
                "total_expenses": 0,
                "balance": 0
            }

        total_income = df[df["amount"] > 0]["amount"].sum()
        total_expenses = df[df["amount"] < 0]["amount"].sum()
        balance = total_income + total_expenses

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