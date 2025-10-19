# db_store.py
from typing import List
import pandas as pd
from sqlalchemy.orm import Session
from db import SessionLocal, init_db
from models import Transactions
from categorizer import categorize_text


# Initialize DB on import (idempotent)
init_db()

ALLOWED = ["date", "description", "merchant", "amount", "category"]

def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    else:
        df["amount"] = 0.0
    data = {col: df[col] if col in df.columns else [None] * len(df) for col in ALLOWED}
    df2 = pd.DataFrame(data)
    df2 = df2.where(pd.notnull(df2), None)
    return df2

def _auto_fill_categories(df):
    """
    Fill in missing 'category' column values using categorize_text.
    """
    for i, row in df.iterrows():
        if not row.get('category'):
            text = f"{row.get('merchant', '')} {row.get('description', '')}"
            df.at[i, 'category'] = categorize_text(text)
            

def save_dataframe(df: pd.DataFrame):
    """
    Save a pandas DataFrame to the transactions table using SQLAlchemy.
    Uses bulk insert for speed.
    """
    df2 = _normalize_df(df)
    _auto_fill_categories(df2)
    # Convert DataFrame to list of dicts for bulk_insert_mappings
    records = df2.to_dict(orient="records")
    # Map keys to model column names directly
    session: Session = SessionLocal()
    try:
        session.bulk_insert_mappings(Transactions, records)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def list_transactions(limit: int = 100) -> List[dict]:
    """
    Return rows as list of dicts, newest first.
    """
    session: Session = SessionLocal()
    try:
        q = session.query(Transactions).order_by(Transactions.id.desc()).limit(int(limit))
        rows = []
        for r in q:
            rows.append({
                "id": r.id,
                "date": r.date,
                "description": r.description,
                "merchant": r.merchant,
                "amount": r.amount,
                "category": r.category
            })
        return rows
    finally:
        session.close()



def clear_transactions():
    """
    Dangerous: delete all rows (for testing).
    """
    session: Session = SessionLocal()
    try:
        session.query(Transactions).delete()
        session.commit()
    finally:
        session.close()
