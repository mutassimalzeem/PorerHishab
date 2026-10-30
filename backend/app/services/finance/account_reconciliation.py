from datetime import date
from zoneinfo import ZoneInfo
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.transactions import Transaction


def _compute_status_and_confidence(
    *,
    current_balance: Decimal | None,
    opening_balance: Decimal | None,
    opening_balance_date,
    latest_transaction_balance: Decimal | None,
    derived_balance: Decimal | None,
    difference: Decimal | None,
    transaction_count: int,
) -> tuple[str, str, str]:
    """Compute status, confidence, and message based on reconciliation state."""
    
    # Test 1: No information at all
    if (current_balance is None and opening_balance is None and 
        latest_transaction_balance is None and transaction_count == 0):
        return "unreconciled", "unknown", "No balance information available"
    
    # Test 6: Reported only - has current_balance but no way to derive
    if (current_balance is not None and derived_balance is None and 
        opening_balance is None and latest_transaction_balance is None):
        return "reported_only", "low", "Balance reported by user; no transaction history to verify"
    
    # Test 2: Transaction snapshot - derived from latest transaction balance
    if derived_balance is not None and latest_transaction_balance is not None and opening_balance is None:
        if derived_balance == latest_transaction_balance:
            return "transaction_snapshot", "medium", f"Derived from latest transaction balance ({latest_transaction_balance})"
    
    # Test 3: Derived from opening balance + transactions
    if derived_balance is not None and opening_balance is not None and opening_balance_date is not None:
        # Check if matches reported balance
        if current_balance is not None and difference is not None:
            if difference == 0:
                return "reconciled", "high", "Reported balance matches derived balance exactly"
            else:
                return "mismatch", "low", f"Reported balance differs from derived balance by {difference}"
        else:
            return "derived_from_opening", "medium", f"Derived from opening balance ({opening_balance}) and {transaction_count} transactions"
    
    # Test 4 & 5: Has both reported and derived
    if current_balance is not None and derived_balance is not None and difference is not None:
        if difference == 0:
            return "reconciled", "high", "Reported balance matches derived balance exactly"
        else:
            return "mismatch", "low", f"Reported balance differs from derived balance by {difference}"
    
    # Default fallback
    if derived_balance is not None:
        return "derived", "medium", f"Derived balance: {derived_balance}"
    elif current_balance is not None:
        return "reported_only", "low", "Balance reported by user"
    
    return "unreconciled", "unknown", "Unable to determine balance status"


def reconcile_account_balance(
    db: Session,
    *,
    account: Account,
    user_id: int,
    as_of: date | None = None,
) -> dict:
    """Reconcile stored balances using Decimal arithmetic and separate fee costs."""
    if account.user_id != user_id:
        raise ValueError("Account does not belong to the user")

    query = db.query(Transaction).filter(
        Transaction.account_id == account.id, Transaction.user_id == user_id)
    if as_of is not None:
        query = query.filter(Transaction.date <= as_of)
    transactions = (
        query
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    latest_transaction = transactions[-1] if transactions else None
    latest_transaction_balance = (
        latest_transaction.balance if latest_transaction is not None else None
    )
    opening = account.opening_balance
    opening_date = account.opening_balance_date
    reported = account.current_balance
    if as_of is not None:
        if opening_date is not None and opening_date > as_of:
            opening = opening_date = None
        stamp = account.balance_as_of
        if stamp is not None:
            stamp = stamp.replace(tzinfo=ZoneInfo("UTC")) if stamp.tzinfo is None else stamp
            if stamp.astimezone(ZoneInfo("Asia/Dhaka")).date() > as_of:
                reported = None
    derived_balance = None
    if opening is not None and opening_date is not None:
        # Amounts are signed; fees are stored separately as positive costs.
        # CSV ingestion leaves fees at zero and preserves its supplied amount.
        derived_balance = opening + sum(
            (
                transaction.amount - transaction.fee
                for transaction in transactions
                if transaction.date >= opening_date
            ),
            Decimal("0.00"),
        )
    elif latest_transaction_balance is not None:
        derived_balance = latest_transaction_balance

    difference = None
    if reported is not None and derived_balance is not None:
        difference = reported - derived_balance

    status, confidence, message = _compute_status_and_confidence(
        current_balance=reported,
        opening_balance=opening,
        opening_balance_date=opening_date,
        latest_transaction_balance=latest_transaction_balance,
        derived_balance=derived_balance,
        difference=difference,
        transaction_count=len(transactions),
    )

    return {
        "account_id": account.id,
        "account_name": account.name,
        "currency": account.currency,
        "reported_balance": reported,
        "reported_balance_as_of": account.balance_as_of,
        "balance_source": account.balance_source,
        "opening_balance": account.opening_balance,
        "opening_balance_date": account.opening_balance_date,
        "latest_transaction_date": latest_transaction.date if latest_transaction else None,
        "latest_transaction_balance": latest_transaction_balance,
        "derived_balance": derived_balance,
        "transaction_count": len(transactions),
        "difference": difference,
        "status": status,
        "confidence": confidence,
        "message": message,
    }
