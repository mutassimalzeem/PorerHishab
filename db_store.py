# db_store.py
from typing import List
import pandas as pd
from sqlalchemy.orm import Session
from db import SessionLocal, init_db
from models import Transactions
from categorizer import categorize_text
from sqlalchemy import or_, and_


# Initialize DB on import (idempotent)
init_db()

ALLOWED = ["date", "description", "merchant", "amount", "category"]

def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Ensure python objects and convert any NA/<NA>/NaN → None *first*
    df = df.astype(object).where(pd.notnull(df), None)

    # Trim headers
    df.columns = [str(c).strip() for c in df.columns]

    ALLOWED = ["date", "description", "merchant", "amount", "category"]
    data = {col: (df[col] if col in df.columns else [None] * len(df)) for col in ALLOWED}
    df2 = pd.DataFrame(data).astype(object).where(pd.notnull(df), None)

    # Coerce amount to float
    df2["amount"] = pd.to_numeric(df2.get("amount", 0.0), errors="coerce").fillna(0.0)

    # Dates → ISO strings if present
    if "date" in df2.columns:
        df2["date"] = pd.to_datetime(df2["date"], errors="coerce").dt.date.astype(object)
        df2["date"] = df2["date"].where(pd.notnull(df2["date"]), None)

    # Strip strings
    for col in ["description", "merchant", "category"]:
        if col in df2.columns:
            df2[col] = df2[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

    # Final guard: replace any residual Pandas NA with None
    df2 = df2.astype(object).where(pd.notnull(df2), None)
    return df2



def _is_missing(val) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and val.strip() == "":
        return True
    
    try:
        return pd.isna(val)         # pd.isna handles pd.NA, numpy.nan, etc.
    except Exception:
        return False
    

def _auto_fill_categories(df: pd.DataFrame) -> None:
    for i, row in df.iterrows():
        cat = row.get("category", None)
        # Missing if None or empty/whitespace string
        if cat is None or (isinstance(cat, str) and cat.strip() == ""):
            merchant = row.get("merchant") or ""
            desc = row.get("description") or ""
            text = f"{merchant} {desc}".strip()
            df.at[i, "category"] = categorize_text(text) or "Other"


def save_dataframe(df: pd.DataFrame, user_id: int | None = None) -> None:

    df2 = _normalize_df(df)
    _auto_fill_categories(df2)
    # Convert DataFrame to list of dicts for bulk_insert_mappings

    if user_id is not None:
        df2["user_id"] = int(user_id)

    records = df2.to_dict(orient="records")
    # Map keys to model column names directly
    session: Session = SessionLocal()
    try:

        CHUNK = 2000        #   Safe for big CSVs
        for i in range(0, len(records), CHUNK):

            session.bulk_insert_mappings(Transactions, records[i: i + CHUNK])
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def list_transactions(limit: int = 100, user_id: int | None = None) -> List[dict]:
    """
    Return rows as list of dicts, newest first.
    """
    session: Session = SessionLocal()
    try:
        q = session.query(Transactions)
        if user_id is not None:
            q = q.filter(Transactions.user_id == int(user_id))
        q = q.order_by(Transactions.id.desc()).limit(int(limit))
        
        rows = []
        for r in q:
            rows.append({
                "id": r.id,
                "date": r.date,
                "description": r.description,
                "merchant": r.merchant,
                "amount": float(r.amount or 0.0),
                "category": r.category,
                "user_id": getattr(r, "user_id", None),
            })
        return rows
    finally:
        session.close()


def search_transactions(
        user_id: int,
        q: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        min_amount : float | None = None,
        max_amount : float | None = None,
        categories: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        sort: str = "desc"
) -> list[dict]:
    session: Session = SessionLocal()

    try:
        qset = session.query(Transactions).filter(Transactions.user_id == int(user_id))

        # text match (case-insensitive) on merchant OR description
        if q:
            like = f"%{q.strip()}%"
            qset = qset.filter(
                or_(
                    Transactions.merchant.ilike(like),
                    Transactions.description.ilike(like),
                )
            )

        if start_date:
            qset = qset.filter(Transactions.date >= start_date)

        if end_date:
            qset = qset.filter(Transactions.date <= end_date)

        #   Amount Filters
        if min_amount is not None:
            qset = qset.filter(Transactions.amount >= float(min_amount))
        if max_amount is not None:
            qset = qset.filter(Transactions.amount <= float(max_amount))

        #   category Filters (any of)
        if categories:
            qset = qset.filter(Transactions.category.in_(categories))

        #   Ordering
        if sort == "asc":
            qset = qset.order_by(Transactions.date.asc(), Transactions.id.asc())
        else:
            qset = qset.order_by(Transactions.date.desc(), Transactions.id.desc())

        qset = qset.offset(int(offset)).limit(int(limit))


        rows = []
        for r in qset:
            rows.append({
                "id": r.id,
                "date": r.date,
                "description": r.description,
                "merchant": r.merchant,
                "amount": float(r.amount or 0.0),
                "category": r.category,
                "user_id": getattr(r, "user_id", None),
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
