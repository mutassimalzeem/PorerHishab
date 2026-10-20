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
    
    query = db.query(Transaction).filter(Transaction.user_id == user_id)

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