"""All reconciliation queries are explicitly scoped to their owner."""
from fastapi import HTTPException
from sqlalchemy import or_
from app.models.account import Account
from app.models.user import User
from app.models.transactions import Transaction
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.obligation_allocation import ObligationAllocation

def lock_owner(db, user_id):
    # PostgreSQL row lock serializes confirmations, revocations and obligation edits.
    db.query(User).filter(User.id == user_id).with_for_update().one()

def item_for_user(db, user_id, item_id):
    item = db.query(ScheduledCashflowItem).filter_by(id=item_id, user_id=user_id).first()
    if item is None:
        raise HTTPException(404, "Scheduled cashflow item not found")
    return item

def transaction_for_user(db, user_id, transaction_id):
    row = db.query(Transaction).filter_by(id=transaction_id, user_id=user_id).first()
    if row is None:
        raise HTTPException(404, "Transaction not found")
    return row

def allocations(db, user_id, item_id=None, active=True):
    query = db.query(ObligationAllocation).filter_by(user_id=user_id)
    if item_id is not None:
        query = query.filter_by(item_id=item_id)
    if active is not None:
        query = query.filter_by(active=active)
    return query.order_by(ObligationAllocation.id).all()


def eligible_transactions(db, user_id):
    accounts = db.query(Account.id).filter_by(user_id=user_id, currency="BDT")
    return db.query(Transaction).filter(
        Transaction.user_id == user_id,
        or_(Transaction.account_id.is_(None), Transaction.account_id.in_(accounts)),
    ).order_by(Transaction.date, Transaction.id).all()


def is_bdt_transaction(db, user_id, tx):
    return tx.account_id is None or db.query(Account.id).filter_by(
        id=tx.account_id, user_id=user_id, currency="BDT").first() is not None
