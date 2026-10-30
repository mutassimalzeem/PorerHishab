from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Account, Transaction, User
from app.schemas.account_reconciliation import AccountBalanceReconciliation, AccountBalanceUpdate
from app.services.finance.account_reconciliation import reconcile_account_balance


@pytest.fixture
def data():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="reconciliation@example.com", hashed_password="test")
        db.add(user)
        db.flush()
        account = Account(user_id=user.id, name="Cash", currency="BDT")
        db.add(account)
        db.flush()
        yield db, account, user
    engine.dispose()


def test_signed_amounts_separate_positive_fees_and_opening_date(data):
    db, account, user = data
    account.opening_balance = Decimal("1000.00")
    account.opening_balance_date = date(2026, 10, 2)
    account.current_balance = Decimal("1100.00")
    other = Account(user_id=account.user_id, name="Other")
    db.add(other)
    db.flush()
    for day, amount, fee, account_id in [
        (1, "999", "0", account.id),
        (2, "-100", "5", account.id),
        (3, "200", "0", account.id),
        (3, "9999", "0", other.id),
    ]:
        db.add(Transaction(user_id=account.user_id, account_id=account_id,
                           date=date(2026, 10, day), amount=Decimal(amount), fee=Decimal(fee)))
    db.flush()
    result = reconcile_account_balance(db, account=account, user_id=account.user_id)
    assert result["derived_balance"] == Decimal("1095.00")
    assert result["difference"] == Decimal("5.00")
    assert result["transaction_count"] == 3
    assert AccountBalanceReconciliation.model_validate(result).account_id == account.id


def test_latest_balance_tie_break_and_missing_balance(data):
    db, account, user = data
    assert reconcile_account_balance(db, account=account, user_id=account.user_id)["derived_balance"] is None
    first = Transaction(user_id=account.user_id, account_id=account.id,
                        date=date(2026, 10, 1), amount=Decimal("10"), balance=Decimal("50"))
    db.add(first)
    db.flush()
    last = Transaction(user_id=account.user_id, account_id=account.id,
                       date=first.date, amount=Decimal("10"), balance=Decimal("60"))
    db.add(last)
    db.flush()
    assert reconcile_account_balance(db, account=account, user_id=account.user_id)["derived_balance"] == Decimal("60")
    last.balance = None
    db.flush()
    assert reconcile_account_balance(db, account=account, user_id=account.user_id)["derived_balance"] is None
    with pytest.raises(ValueError):
        reconcile_account_balance(db, account=account, user_id=account.user_id + 1)


def test_balance_schema_rejects_fractional_cents():
    with pytest.raises(ValueError):
        AccountBalanceUpdate(current_balance="1.001", balance_source="manual",
                             balance_as_of="2026-10-01T00:00:00Z")


# Test 1: No information at all
def test_no_information_unreconciled(data):
    """Test 1 — no information
    current_balance = None
    opening_balance = None
    transactions = []
    → status = unreconciled
    → confidence = unknown
    """
    db, account, user = data
    result = reconcile_account_balance(db, account=account, user_id=account.user_id)
    
    assert result["derived_balance"] is None
    assert result["difference"] is None
    assert result["transaction_count"] == 0
    assert result["status"] == "unreconciled"
    assert result["confidence"] == "unknown"
    assert "No balance information available" in result["message"]


# Test 2: Latest transaction has balance
def test_latest_transaction_balance_snapshot(data):
    """Test 2 — latest transaction has balance
    transaction.balance = 15000
    → status = transaction_snapshot
    → derived_balance = 15000
    """
    db, account, user = data
    txn = Transaction(
        user_id=account.user_id,
        account_id=account.id,
        date=date(2026, 1, 15),
        amount=Decimal("-500"),
        balance=Decimal("15000"),
    )
    db.add(txn)
    db.flush()
    
    result = reconcile_account_balance(db, account=account, user_id=account.user_id)
    
    assert result["derived_balance"] == Decimal("15000")
    assert result["status"] == "transaction_snapshot"
    assert result["confidence"] == "medium"
    assert "15000" in result["message"]


# Test 3: Opening balance + transactions
def test_opening_balance_plus_transactions(data):
    """Test 3 — opening balance + transactions
    opening = 20,000
    -2,000
    +5,000
    -1,000
    → derived = 22,000
    """
    db, account, user = data
    account.opening_balance = Decimal("20000")
    account.opening_balance_date = date(2026, 1, 1)
    db.flush()
    
    txns = [
        Transaction(user_id=account.user_id, account_id=account.id, date=date(2026, 1, 5), amount=Decimal("-2000")),
        Transaction(user_id=account.user_id, account_id=account.id, date=date(2026, 1, 10), amount=Decimal("5000")),
        Transaction(user_id=account.user_id, account_id=account.id, date=date(2026, 1, 15), amount=Decimal("-1000")),
    ]
    db.add_all(txns)
    db.flush()
    
    result = reconcile_account_balance(db, account=account, user_id=account.user_id)
    
    assert result["derived_balance"] == Decimal("22000")
    assert result["transaction_count"] == 3
    assert result["status"] == "derived_from_opening"
    assert result["confidence"] == "medium"


# Test 4: Confirmed balance matches
def test_confirmed_balance_matches_reconciled(data):
    """Test 4 — confirmed balance matches
    reported = 22,000
    derived = 22,000
    → status = reconciled
    → difference = 0
    → confidence = high
    """
    db, account, user = data
    account.opening_balance = Decimal("20000")
    account.opening_balance_date = date(2026, 1, 1)
    account.current_balance = Decimal("22000")
    db.flush()
    
    txns = [
        Transaction(user_id=account.user_id, account_id=account.id, date=date(2026, 1, 5), amount=Decimal("-2000")),
        Transaction(user_id=account.user_id, account_id=account.id, date=date(2026, 1, 10), amount=Decimal("5000")),
        Transaction(user_id=account.user_id, account_id=account.id, date=date(2026, 1, 15), amount=Decimal("-1000")),
    ]
    db.add_all(txns)
    db.flush()
    
    result = reconcile_account_balance(db, account=account, user_id=account.user_id)
    
    assert result["derived_balance"] == Decimal("22000")
    assert result["reported_balance"] == Decimal("22000")
    assert result["difference"] == Decimal("0")
    assert result["status"] == "reconciled"
    assert result["confidence"] == "high"
    assert "matches" in result["message"].lower()


# Test 5: Mismatch
def test_mismatch_reported_vs_derived(data):
    """Test 5 — mismatch
    reported = 25,000
    derived = 22,000
    → status = mismatch
    → difference = 3,000
    → confidence = low
    """
    db, account, user = data
    account.opening_balance = Decimal("20000")
    account.opening_balance_date = date(2026, 1, 1)
    account.current_balance = Decimal("25000")
    db.flush()
    
    txns = [
        Transaction(user_id=account.user_id, account_id=account.id, date=date(2026, 1, 5), amount=Decimal("-2000")),
        Transaction(user_id=account.user_id, account_id=account.id, date=date(2026, 1, 10), amount=Decimal("5000")),
        Transaction(user_id=account.user_id, account_id=account.id, date=date(2026, 1, 15), amount=Decimal("-1000")),
    ]
    db.add_all(txns)
    db.flush()
    
    result = reconcile_account_balance(db, account=account, user_id=account.user_id)
    
    assert result["derived_balance"] == Decimal("22000")
    assert result["reported_balance"] == Decimal("25000")
    assert result["difference"] == Decimal("3000")
    assert result["status"] == "mismatch"
    assert result["confidence"] == "low"
    assert "3000" in result["message"]


# Test 6: Insufficient history
def test_insufficient_history_reported_only(data):
    """Test 6 — insufficient history
    reported = 25,000
    opening = None
    transaction balances = None
    → status = reported_only
    """
    db, account, user = data
    account.current_balance = Decimal("25000")
    txns = [
        Transaction(user_id=account.user_id, account_id=account.id, date=date(2026, 1, 5), amount=Decimal("-2000")),
        Transaction(user_id=account.user_id, account_id=account.id, date=date(2026, 1, 10), amount=Decimal("5000")),
    ]
    db.add_all(txns)
    db.flush()
    
    result = reconcile_account_balance(db, account=account, user_id=account.user_id)
    
    assert result["reported_balance"] == Decimal("25000")
    assert result["derived_balance"] is None
    assert result["status"] == "reported_only"
    assert result["confidence"] == "low"
    assert "reported" in result["message"].lower()


# Test 7: User isolation
def test_user_isolation_raises_404(data):
    """Test 7 — user isolation
    User A must never be able to reconcile User B's account.
    Expected: 404 Account not found
    not a 403 or leaked account information.
    """
    db, account, user_a = data
    
    user_b = User(email="user_b@example.com", hashed_password="test")
    db.add(user_b)
    db.flush()
    
    with pytest.raises(ValueError) as exc_info:
        reconcile_account_balance(db, account=account, user_id=user_b.id)
    
    assert "Account does not belong to the user" in str(exc_info.value)


# Test 8: Future transaction isn't included in opening calculation
def test_future_transaction_excluded_from_opening_calculation(data):
    """Test 8 — future transaction isn't included in opening calculation
    If:
    opening_date = 2026-01-01
    2025-12-31  -500
    2026-01-10 -1000
    only the 2026-01-10 transaction participates.
    """
    db, account, user = data
    account.opening_balance = Decimal("10000")
    account.opening_balance_date = date(2026, 1, 1)
    db.flush()
    
    txn_before = Transaction(
        user_id=account.user_id,
        account_id=account.id,
        date=date(2025, 12, 31),
        amount=Decimal("-500"),
    )
    txn_after = Transaction(
        user_id=account.user_id,
        account_id=account.id,
        date=date(2026, 1, 10),
        amount=Decimal("-1000"),
    )
    db.add_all([txn_before, txn_after])
    db.flush()
    
    result = reconcile_account_balance(db, account=account, user_id=account.user_id)
    
    assert result["derived_balance"] == Decimal("9000")
    assert result["transaction_count"] == 2
