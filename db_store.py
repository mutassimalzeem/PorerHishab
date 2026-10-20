
"""Database storage operations for Zyra transactions."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.transactions import Transaction
from categorizer import categorize_text


ALLOWED = ["date", "description", "merchant", "amount", "category"]


def _is_missing(value: Any) -> bool:
    """Return True for None, NaN, pandas NA, and blank strings."""
    if value is None:
        return True

    if isinstance(value, str) and not value.strip():
        return True

    try:
        result = pd.isna(value)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return False


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize CSV data and validate required transaction fields."""
    df = df.copy()
    df.columns = [str(column).strip() for column in df.columns]

    if df.empty:
        return pd.DataFrame(columns=ALLOWED)

    if len(df.columns) != len(set(df.columns)):
        raise ValueError("The CSV contains duplicate column names.")

    required = {"date", "amount"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"CSV is missing required column(s): {', '.join(sorted(missing))}"
        )

    normalized = pd.DataFrame(index=df.index)

    for column in ALLOWED:
        normalized[column] = (
            df[column] if column in df.columns else None
        )

    # Parse dates; invalid or missing dates must not be stored.
    parsed_dates = pd.to_datetime(normalized["date"], errors="coerce")
    invalid_dates = parsed_dates.isna()

    if invalid_dates.any():
        rows = [int(index) + 2 for index in df.index[invalid_dates]]
        raise ValueError(
            f"Missing or invalid transaction date(s) at CSV row(s): {rows}"
        )

    normalized["date"] = parsed_dates.dt.date

    # Convert amounts directly to Decimal to avoid storing binary floats.
    amounts: list[Decimal] = []

    for index, value in normalized["amount"].items():
        if _is_missing(value):
            raise ValueError(
                f"Missing transaction amount at CSV row {int(index) + 2}."
            )

        try:
            amount = Decimal(str(value).strip().replace(",", ""))
        except (InvalidOperation, ValueError):
            raise ValueError(
                f"Invalid transaction amount at CSV row {int(index) + 2}."
            ) from None

        if not amount.is_finite():
            raise ValueError(
                f"Non-finite transaction amount at CSV row {int(index) + 2}."
            )

        amounts.append(amount)

    normalized["amount"] = amounts

    # Convert pandas missing values to None and trim text fields.
    for column in ["description", "merchant", "category"]:
        normalized[column] = normalized[column].map(
            lambda value: (
                value.strip()
                if isinstance(value, str)
                else None if _is_missing(value) else value
            )
        )

    normalized = normalized.astype(object).where(
        pd.notnull(normalized), None
    )

    return normalized


def _auto_fill_categories(df: pd.DataFrame) -> None:
    """Categorize rows whose category was not supplied."""
    for index, row in df.iterrows():
        if _is_missing(row.get("category")):
            merchant = row.get("merchant") or ""
            description = row.get("description") or ""
            text = f"{merchant} {description}".strip()

            df.at[index, "category"] = categorize_text(text) or "Other"


def save_dataframe(
    df: pd.DataFrame,
    user_id: int | None = None,
) -> None:
    """Validate and save imported transactions for one user."""
    if user_id is None:
        raise ValueError("user_id is required to save transactions.")

    normalized = _normalize_df(df)

    if normalized.empty:
        return

    _auto_fill_categories(normalized)

    session: Session = SessionLocal()

    try:
        records = normalized.to_dict(orient="records")

        # No account is assigned by the current CSV upload endpoint.
        transactions = [
            Transaction(
                user_id=int(user_id),
                account_id=None,
                date=record["date"],
                description=record["description"],
                merchant=record["merchant"],
                amount=record["amount"],
                category=record["category"],
            )
            for record in records
        ]

        session.add_all(transactions)
        session.commit()

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


def _serialize_transaction(transaction: Transaction) -> dict:
    """Preserve the response shape expected by the current API."""
    return {
        "id": transaction.id,
        "date": transaction.date,
        "description": transaction.description,
        "merchant": transaction.merchant,
        "amount": float(transaction.amount or 0),
        "category": transaction.category,
        "user_id": transaction.user_id,
    }


def list_transactions(
    limit: int = 100,
    user_id: int | None = None,
) -> list[dict]:
    """Return newest transactions first, optionally scoped to a user."""
    session: Session = SessionLocal()

    try:
        query = session.query(Transaction)

        if user_id is not None:
            query = query.filter(Transaction.user_id == int(user_id))

        rows = (
            query.order_by(Transaction.id.desc())
            .limit(max(0, int(limit)))
            .all()
        )

        return [_serialize_transaction(row) for row in rows]

    finally:
        session.close()


def search_transactions(
    user_id: int,
    q: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    categories: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
    sort: str = "desc",
) -> list[dict]:
    """Search transactions belonging to the specified user."""
    session: Session = SessionLocal()

    try:
        query = session.query(Transaction).filter(
            Transaction.user_id == int(user_id)
        )

        if q and q.strip():
            pattern = f"%{q.strip()}%"
            query = query.filter(
                or_(
                    Transaction.merchant.ilike(pattern),
                    Transaction.description.ilike(pattern),
                )
            )

        if start_date:
            query = query.filter(
                Transaction.date >= date.fromisoformat(start_date)
            )

        if end_date:
            query = query.filter(
                Transaction.date <= date.fromisoformat(end_date)
            )

        if min_amount is not None:
            query = query.filter(
                Transaction.amount >= Decimal(str(min_amount))
            )

        if max_amount is not None:
            query = query.filter(
                Transaction.amount <= Decimal(str(max_amount))
            )

        if categories:
            query = query.filter(Transaction.category.in_(categories))

        if sort.lower() == "asc":
            query = query.order_by(
                Transaction.date.asc(),
                Transaction.id.asc(),
            )
        else:
            query = query.order_by(
                Transaction.date.desc(),
                Transaction.id.desc(),
            )

        rows = (
            query.offset(max(0, int(offset)))
            .limit(max(0, int(limit)))
            .all()
        )

        return [_serialize_transaction(row) for row in rows]

    finally:
        session.close()


def clear_transactions() -> None:
    """Delete all transactions. Use only in an isolated test database."""
    session: Session = SessionLocal()

    try:
        session.query(Transaction).delete()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
