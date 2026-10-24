from datetime import date
from decimal import Decimal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.transactions import Transaction


def create_transactions(
    db: Session,
    transactions: list[Transaction]) -> list[Transaction]:
    
    db.add_all(transactions)
    db.commit()

    for transaction in transactions:
        db.refresh(transaction)

    return transactions


def _apply_transaction_filters(
    query,
    user_id: int,
    q: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    categories: list[str] | None = None,
):
    """Apply the shared search filters to a ``Transaction`` query.

    Used by both :func:`search_transactions` (rows) and
    :func:`count_transactions` (total), so the two always agree on what
    matches.
    """
    query = query.filter(Transaction.user_id == user_id)

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
        query = query.filter(
            Transaction.category.in_(categories)
        )

    return query


def list_transactions(
    db: Session,
    user_id: int,
    limit: int = 100,
) -> list[Transaction]:
    return (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.id.desc())
        .limit(max(0, int(limit)))
        .all()
    )


def list_transactions_in_range(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None) -> list[Transaction]:

    """All of a user's transactions, oldest first, optionally date-bounded.

    Ordered ascending by ``(date, id)`` so analytics code (cash-flow
    timeline, recurring detection) sees a stable chronological input.
    """

    query = db.query(Transaction).filter(Transaction.user_id == user_id)

    if start_date is not None:
        query = query.filter(Transaction.date >= start_date)

    if end_date is not None:
        query = query.filter(Transaction.date <= end_date)

    return (query.order_by(Transaction.date.asc(), Transaction.id.asc()).all())


def count_transactions(
    db: Session,
    user_id: int,
    q: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    categories: list[str] | None = None,
) -> int:
    """Number of transactions matching the search filters (ignores paging)."""
    query = _apply_transaction_filters(
        db.query(Transaction),
        user_id,
        q=q,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        max_amount=max_amount,
        categories=categories,
    )

    return query.count()


def search_transactions(
    db: Session,
    user_id: int,
    q: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    categories: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
    sort: str = "desc") -> list[Transaction]:

    query = _apply_transaction_filters(
        db.query(Transaction),
        user_id,
        q=q,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        max_amount=max_amount,
        categories=categories,
    )

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

    return (
        query
        .offset(max(0, int(offset)))
        .limit(max(0, int(limit)))
        .all()
    )


def get_transaction_for_user(db: Session, transaction_id: int, user_id: int) -> Transaction | None:
    
    return (db.query(Transaction).filter(Transaction.id == transaction_id,
                                         Transaction.user_id == user_id).first())


def create_category_correction(
    db: Session,
    correction,
):
    db.add(correction)
    db.flush()

    return correction


from app.models.merchant_preference import MerchantCategoryPreference

def get_merchant_category_preference(
    db: Session,
    *,
    user_id: int,
    normalized_merchant: str,
) -> MerchantCategoryPreference | None:
    return (
        db.query(MerchantCategoryPreference)
        .filter(
            MerchantCategoryPreference.user_id == user_id,
            MerchantCategoryPreference.normalized_merchant == normalized_merchant,
        )
        .first()
    )

def upsert_merchant_category_preference(
    db: Session,
    *,
    user_id: int,
    normalized_merchant: str,
    category: str,
) -> MerchantCategoryPreference:
    preference = get_merchant_category_preference(
        db,
        user_id=user_id,
        normalized_merchant=normalized_merchant,
    )

    if preference is None:
        preference = MerchantCategoryPreference(
            user_id=user_id,
            normalized_merchant=normalized_merchant,
            category=category,
            correction_count=1,
        )
        db.add(preference)
    else:
        preference.category = category
        preference.correction_count += 1

    db.flush()

    return preference