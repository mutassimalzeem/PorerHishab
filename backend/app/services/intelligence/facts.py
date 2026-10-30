"""Deterministic, user-scoped financial facts shared across the engine (AI-13).

These DB-facing aggregates were previously private to
``app.services.finance.coach`` and duplicated conceptually elsewhere. They
now live here so the intelligence engine, the coach, grounded chat and
future consumers all read one implementation.

Scope rules (unchanged, on purpose):

* every query is filtered by ``user_id`` — a user can never observe another
  user's records;
* account-linked records are included only for the user's BDT accounts;
  unlinked imported records are assumed BDT;
* money is ``Decimal`` quantized half-up to two places;
* sign convention: positive amounts are income, negative amounts are
  expenses. Aggregate surfaces report expenses as positive magnitudes.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.transactions import Transaction
from app.schemas.coach import Coverage
from app.services.intelligence.periods import money
from decimal import Decimal

#: Preserved verbatim because regression suites and product copy pin it.
LIMITATIONS = [
    "Imported records may be incomplete; observed totals are not proof of full coverage.",
    "No trustworthy current account balance is inferred from transaction history.",
    "Account-linked records are included only for this user's BDT accounts; unlinked imported records are assumed BDT.",
]


def scoped(db: Session, user_id: int, start: date, end: date):
    """This user's records inside an inclusive window, BDT-account aware."""
    if user_id <= 0 or start > end:
        raise ValueError("Invalid financial query scope")
    owned_bdt_accounts = db.query(Account.id).filter(
        Account.user_id == user_id, Account.currency == "BDT")
    return db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.date >= start,
        Transaction.date <= end,
        or_(Transaction.account_id.is_(None),
            Transaction.account_id.in_(owned_bdt_accounts)),
    )


def totals(
    db: Session,
    user_id: int,
    start: date,
    end: date,
    category: str | None = None,
) -> dict:
    """Income, expenses, net and a coverage statement for one window.

    ``None`` amounts mean "no records observed" — never zero.
    """
    query = scoped(db, user_id, start, end)
    if category:
        query = query.filter(func.lower(Transaction.category) == category.lower())
    count, first, last, income, expenses = query.with_entities(
        func.count(Transaction.id),
        func.min(Transaction.date),
        func.max(Transaction.date),
        func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)),
        func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0)),
    ).one()

    coverage = Coverage(
        start_date=start,
        end_date=end,
        transaction_count=count,
        first_transaction_date=first,
        last_transaction_date=last,
        limitations=LIMITATIONS,
    )
    return {
        "income": money(income) if count else None,
        "expenses": money(expenses) if count else None,
        "net": money(income - expenses) if count else None,
        "coverage": coverage.model_dump(mode="json"),
    }


def grouped_expenses(
    db: Session,
    user_id: int,
    start: date,
    end: date,
    group: str = "category",
    limit: int = 10,
) -> list[dict]:
    """Spending magnitudes grouped by category or merchant, ranked."""
    column = Transaction.category if group == "category" else Transaction.merchant
    label = func.coalesce(column, "Uncategorized" if group == "category" else "Unknown merchant")
    amount = func.sum(-Transaction.amount)
    rows = scoped(db, user_id, start, end).filter(Transaction.amount < 0).with_entities(
        label, amount, func.count(Transaction.id),
    ).group_by(label).order_by(amount.desc(), label.asc()).limit(limit).all()

    return [
        {group: name, "expenses": money(total), "transaction_count": count}
        for name, total, count in rows
    ]


def scheduled_cashflow_items(
    db: Session,
    user_id: int,
    start: date,
    end: date,
    *,
    kind: str | None = None,
    status: str = "scheduled",
    limit: int | None = None,
) -> list[ScheduledCashflowItem]:
    """This user's planned cashflow rows inside an inclusive due-date window.

    Only the requested ``status`` is returned (default ``scheduled``): paid
    rows are past facts and cancelled rows are not obligations, so neither
    may surface as an upcoming obligation.
    """
    query = db.query(ScheduledCashflowItem).filter(
        ScheduledCashflowItem.user_id == user_id,
        ScheduledCashflowItem.status == status,
        ScheduledCashflowItem.due_date >= start,
        ScheduledCashflowItem.due_date <= end,
    )
    if kind is not None:
        query = query.filter(ScheduledCashflowItem.kind == kind)
    query = query.order_by(ScheduledCashflowItem.due_date, ScheduledCashflowItem.id)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def scheduled_totals(db: Session, user_id: int, start: date, end: date):
    """ ``(expenses, income)`` totals of *scheduled* (unpaid, uncancelled) plans.

    The pair order and money rounding are preserved from the original coach
    implementation so regression suites keep passing.
    """
    from app.models.obligation_allocation import ObligationAllocation
    allocated = db.query(
        ObligationAllocation.item_id,
        func.sum(ObligationAllocation.amount).label("allocated"),
    ).filter_by(user_id=user_id, active=True).group_by(ObligationAllocation.item_id).subquery()
    rows = db.query(
        ScheduledCashflowItem.kind,
        func.sum(ScheduledCashflowItem.amount - func.coalesce(allocated.c.allocated, 0)),
    ).outerjoin(allocated, allocated.c.item_id == ScheduledCashflowItem.id).filter(
        ScheduledCashflowItem.user_id == user_id,
        ScheduledCashflowItem.status == "scheduled",
        ScheduledCashflowItem.due_date >= start,
        ScheduledCashflowItem.due_date <= end,
    ).group_by(ScheduledCashflowItem.kind).all()

    default = Decimal("0.00")
    values = {kind_name: money(amount) for kind_name, amount in rows}
    return values.get("expense", default), values.get("income", default)
