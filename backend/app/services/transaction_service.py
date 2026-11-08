import re
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from dataclasses import dataclass

import pandas as pd

from app.core.database import SessionLocal
from app.models.transactions import Transaction
from app.repositories.transaction_repository import create_transactions
from app.services.categorization.budget import (
    CategorizationBudget,
    DEFAULT_CATEGORIZATION_BUDGET,
)
from app.services.categorization.service import categorize_transaction


REQUIRED_COLUMNS = {"date", "amount"}

MAX_CSV_ROWS = 10_000
MAX_CSV_COLUMNS = 30
MAX_CSV_ERRORS = 100
CSV_LLM_BUDGET = DEFAULT_CATEGORIZATION_BUDGET


def normalize_transactions(
    df: pd.DataFrame, *, errors: list[dict] | None = None
) -> pd.DataFrame:
    """
    Normalize raw transaction data into PorerHishab's internal format.
    """
    normalized = df.copy()

    if len(normalized) > MAX_CSV_ROWS:
        raise ValueError(f"CSV exceed the maximum of {MAX_CSV_ROWS} rows.")

    if len(normalized.columns) > MAX_CSV_COLUMNS:
        raise ValueError(f"CSV exceeds the maximum of {MAX_CSV_COLUMNS} columns.")

    missing = REQUIRED_COLUMNS - set(normalized.columns)
    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    # CSV dates must be ISO calendar dates; never guess day/month ordering.
    normalized["date"] = normalized["date"].apply(_parse_date)
    normalized["amount"] = normalized["amount"].apply(_parse_amount)

    if errors is not None:
        for row_number, (_, row) in enumerate(normalized.iterrows(), start=2):
            if len(errors) >= MAX_CSV_ERRORS:
                break

            for field in ("date", "amount"):
                if pd.isna(row[field]):
                    if len(errors) >= MAX_CSV_ERRORS:
                        break

                    errors.append({
                        "row": row_number,
                        "field": field,
                        "message": (
                            "Invalid or missing date: use YYYY-MM-DD (1900 or later)."
                            if field == "date"
                            else "Invalid or missing amount."
                        ),
                    })

    normalized = normalized.dropna(subset=["date", "amount"])

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


def categorize_transactions(
    df: pd.DataFrame,
    *,
    user_id=None,
    db=None,
    budget: CategorizationBudget | None = None,
    llm_budget: int | None = None,
) -> pd.DataFrame:
    """
    Fill missing transaction categories using the existing
    rule-based categorizer and LLM fallback up to the categorization budget.

    When ``user_id`` and ``db`` are provided, per-user merchant
    preferences are checked before rules.
    """
    result = df.copy()

    # Ensure these columns exist even when no row is newly categorized,
    # so skipped (already-categorized) rows still have them as NA.
    for column in ("category_confidence", "category_method", "category_reason"):
        if column not in result.columns:
            result[column] = None

    if budget is None:
        if llm_budget is not None:
            budget = CategorizationBudget(max_calls=max(0, llm_budget))
        else:
            budget = CategorizationBudget()

    for index, row in result.iterrows():
        if row["category"]:
            continue

        categorized = categorize_transaction(
            {
                "merchant": row.get("merchant"),
                "normalized_merchant": row.get("normalized_merchant"),
                "description": row.get("description"),
                "amount": row.get("amount"),
            },
            db=db,
            user_id=user_id,
            allow_llm=budget.can_call(),
            budget=budget,
        )

        result.at[index, "category"] = categorized.category
        result.at[index, "category_confidence"] = categorized.confidence
        result.at[index, "category_method"] = categorized.method
        result.at[index, "category_reason"] = categorized.reason

    return result


@dataclass
class TransactionImportResult:
    rows_received: int
    transactions: list[Transaction]
    errors: list[dict]

    @property
    def rows_persisted(self) -> int:
        return len(self.transactions)

    @property
    def rows_rejected(self) -> int:
        return self.rows_received - self.rows_persisted


def save_transactions(
    df: pd.DataFrame,
    user_id: int,
    *,
    detailed: bool = False,
) -> int | TransactionImportResult:
    """
    Normalize, categorize, and persist transactions.

    Returns a count, or (for the upload endpoint) the actual persisted records.
    CSV has no deduplication key: repeated uploads append duplicate records.
    """
    if user_id is None:
        raise ValueError("user_id is required.")

    errors: list[dict] = []
    normalized = normalize_transactions(df, errors=errors)

    if normalized.empty:
        return TransactionImportResult(len(df), [], errors) if detailed else 0

    db = SessionLocal()

    try:
        budget = CategorizationBudget()
        normalized = categorize_transactions(
            normalized,
            user_id=user_id,
            db=db,
            budget=budget,
        )

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

        persisted = create_transactions(db, transactions)
        return TransactionImportResult(len(df), persisted, errors) if detailed else len(persisted)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _parse_date(value) -> date | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value if value.year >= 1900 else None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value.strip()):
        return None
    try:
        parsed = date.fromisoformat(value.strip())
        return parsed if parsed.year >= 1900 else None
    except ValueError:
        return None


def _parse_amount(value) -> Decimal | None:
    if value is None:
        return None

    if pd.isna(value):
        return None

    # Numeric(14, 2) is the persistence policy. Reject fractional cents and
    # overflow before the database can silently round or truncate an amount.
    raw = str(value).strip()
    if not re.fullmatch(r"[+-]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?", raw):
        return None
    try:
        amount = Decimal(raw.replace(",", ""))
        if not amount.is_finite() or abs(amount) >= Decimal("1000000000000"):
            return None
        if amount != amount.quantize(Decimal("0.01")):
            return None
        return amount
    except (InvalidOperation, ValueError):
        return None
