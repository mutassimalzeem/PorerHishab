from decimal import Decimal, InvalidOperation
from datetime import date

import pandas as pd

from app.core.database import SessionLocal
from app.models.transactions import Transaction
from app.repositories.transaction_repository import create_transactions
from app.services.categorization.service import categorize_transaction


REQUIRED_COLUMNS = {"date", "amount"}


def normalize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize raw transaction data into Zyra's internal format.
    """
    normalized = df.copy()

    missing = REQUIRED_COLUMNS - set(normalized.columns)
    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    normalized["date"] = pd.to_datetime(
        normalized["date"],
        errors="coerce",
    ).dt.date

    normalized["amount"] = normalized["amount"].apply(_parse_amount)

    normalized = normalized.dropna(
        subset=["date", "amount"]
    )

    for column in ["description", "merchant", "normalized_merchant", "category"]:
        if column not in normalized.columns:
            normalized[column] = None

    normalized["description"] = normalized["description"].where(
        normalized["description"].notna(),
        None,
    )

    normalized["normalized_merchant"] = normalized["normalized_merchant"].where(
        normalized["normalized_merchant"].notna(),
        None,
    )

    normalized["merchant"] = normalized["merchant"].where(
        normalized["merchant"].notna(),
        None,
    )

    normalized["category"] = normalized["category"].where(
        normalized["category"].notna(),
        None,
    )

    return normalized


def categorize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill missing transaction categories using the existing
    rule-based categorizer.
    """
    result = df.copy()

    # Ensure these columns exist even when no row is newly categorized,
    # so skipped (already-categorized) rows still have them as NA.
    for column in ("category_confidence", "category_method", "category_reason"):
        if column not in result.columns:
            result[column] = None

    for index, row in result.iterrows():
        if row["category"]:
            continue

        categorized = categorize_transaction(
            {
                "merchant": row.get("merchant"),
                "normalized_merchant": row.get("normalized_merchant"),
                "description": row.get("description"),
                "amount": row.get("amount"),
            }
        )

        result.at[index, "category"] = categorized.category
        result.at[index, "category_confidence"] = categorized.confidence
        result.at[index, "category_method"] = categorized.method
        result.at[index, "category_reason"] = categorized.reason

    return result


def save_transactions(
    df: pd.DataFrame,
    user_id: int,
) -> int:
    """
    Normalize, categorize, and persist transactions.

    Returns the number of transactions created.
    """
    if user_id is None:
        raise ValueError("user_id is required.")

    normalized = normalize_transactions(df)

    if normalized.empty:
        return 0

    normalized = categorize_transactions(normalized)

    transactions = [
        Transaction(
            user_id=int(user_id),
            account_id=None,
            date=row["date"],
            description=row["description"],
            merchant=row["merchant"],
            amount=Decimal(str(row["amount"])),
            
            category=row["category"],
            category_confidence=(Decimal(str(row["category_confidence"])) if row["category_confidence"] is not None
                and not pd.isna(row["category_confidence"])
                else None
            ),
            category_method=row["category_method"],
            category_reason=row["category_reason"],
        )
        for _, row in normalized.iterrows()
    ]

    db = SessionLocal()

    try:
        create_transactions(db, transactions)
        return len(transactions)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _parse_amount(value) -> Decimal | None:
    if value is None:
        return None

    if pd.isna(value):
        return None

    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None