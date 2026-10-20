from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import User, Account, Transaction

TEST_EMAIL = "test@zyra.local"


def cleanup(db):
    """Delete any leftover test rows so the test can rerun.

    Deleting the user cascades to its accounts and transactions
    (ondelete="CASCADE" on both foreign keys).
    """
    db.execute(
        User.__table__.delete().where(User.__table__.c.email == TEST_EMAIL)
    )
    db.commit()


def test_database_relationships():
    db = SessionLocal()

    try:
        # Start clean, in case a previous run crashed mid-test.
        cleanup(db)

        user = User(email=TEST_EMAIL,
                    hashed_password="test-password",
                    full_name="Test User")

        db.add(user)
        db.flush()

        account = Account(user_id=user.id,
                          name="bKash",
                          source="bkash", account_type="mobile_wallet",
                          currency="BDT", current_balance=Decimal("10000.00"))

        db.add(account)
        db.flush()

        transaction = Transaction(
            user_id=user.id, account_id=account.id,
            trx_id="TEST-001",
            date=date.today(),
            description="Foodpanda order",
            merchant="Foodpanda",
            normalized_merchant="Foodpanda",
            amount=Decimal("-850.00"),
            fee=Decimal("0.00"),
            balance=Decimal("9150.00"),
            transaction_type="expense",
            category="Food",
            source="manual",
        )

        db.add(transaction)
        db.commit()

        db.refresh(user)

        assert user.accounts[0].name == "bKash"
        assert user.transactions[0].merchant == "Foodpanda"

    finally:
        # Leave the database as we found it.
        cleanup(db)
        db.close()
