"""PostgreSQL integration tests for transaction storage.

These tests exercise the complete round trip against the **real** database
configured through ``DATABASE_URL``::

    Python -> SQLAlchemy -> PostgreSQL -> SQLAlchemy -> Python

A separate session is used to read the data back so the assertions prove the
rows really landed in PostgreSQL (and not merely in the SQLAlchemy identity
map).

PostgreSQL must be running before executing these tests, e.g.
``docker compose up -d``. See ``README.md`` -> "Setup Backend".
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models import Account, Transaction, User
from app.repositories.transaction_repository import (
    create_transactions,
    list_transactions,
    search_transactions,
)

# Unique per run so that repeated (or parallel) test runs never collide on
# the unique email index.
_RUN_ID = uuid4().hex
USER_A_EMAIL = f"integration-a-{_RUN_ID}@zyra.local"
USER_B_EMAIL = f"integration-b-{_RUN_ID}@zyra.local"

TX_A_FOOD = f"INT-A-FOOD-{_RUN_ID}"
TX_A_SALARY = f"INT-A-SALARY-{_RUN_ID}"
TX_B_FOOD = f"INT-B-FOOD-{_RUN_ID}"


def cleanup() -> None:
    """Delete the test users (cascading to accounts and transactions)."""
    db = SessionLocal()

    try:
        db.execute(
            User.__table__.delete().where(
                User.__table__.c.email.in_([USER_A_EMAIL, USER_B_EMAIL])
            )
        )
        db.commit()
    finally:
        db.close()


def create_user(db, email: str, full_name: str) -> User:
    user = User(
        email=email,
        hashed_password="test-password",
        full_name=full_name,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def test_transaction_round_trip_against_postgres():
    """A transaction survives the full Python -> PostgreSQL -> Python trip."""
    cleanup()

    db = SessionLocal()

    try:
        user = create_user(db, USER_A_EMAIL, "Round Trip User")

        account = Account(
            user_id=user.id,
            name="bKash",
            source="bkash",
            account_type="mobile_wallet",
            currency="BDT",
            current_balance=Decimal("15000.00"),
        )

        db.add(account)
        db.commit()
        db.refresh(account)

        original = Transaction(
            user_id=user.id,
            account_id=account.id,
            trx_id=TX_A_FOOD,
            date=date(2026, 10, 1),
            description="Foodpanda order #42",
            merchant="Foodpanda",
            normalized_merchant="foodpanda",
            amount=Decimal("-850.50"),
            fee=Decimal("27.50"),
            balance=Decimal("9150.00"),
            transaction_type="expense",
            category="Food",

            category_confidence=Decimal("0.950"),
            category_method="rule",
            category_reason="Matched Foodpanda merchant rule.",

            subcategory="Delivery",
            source="manual",
            is_recurring=True,
            raw_data={"sms": "Cash Out Tk1,500", "fee": 27.5},
        )

        create_transactions(db, [original])

        transaction_id = original.id
        user_id = user.id
        account_id = account.id

        # Drop every cached object so the next read has to hit PostgreSQL.
        db.expunge_all()

        fresh = SessionLocal()

        try:
            stored = fresh.execute(
                select(Transaction).where(Transaction.id == transaction_id)
            ).scalar_one()

            # Identity / relationships.
            assert stored.id == transaction_id
            assert stored.user_id == user_id
            assert stored.account_id == account_id
            assert stored.trx_id == TX_A_FOOD

            # Money is NUMERIC(14, 2) -> exact decimal, no float drift.
            assert stored.amount == Decimal("-850.50")
            assert stored.fee == Decimal("27.50")
            assert stored.balance == Decimal("9150.00")

            # Scalar / temporal / JSON / boolean columns.
            assert stored.date == date(2026, 10, 1)
            assert stored.description == "Foodpanda order #42"
            assert stored.merchant == "Foodpanda"
            assert stored.normalized_merchant == "foodpanda"
            assert stored.transaction_type == "expense"
            assert stored.category == "Food"
            assert stored.category_confidence == Decimal("0.950")
            assert stored.category_method == "rule"
            assert stored.category_reason == "Matched Foodpanda merchant rule."
            assert stored.subcategory == "Delivery"
            assert stored.source == "manual"
            assert stored.is_recurring is True
            assert stored.raw_data == {"sms": "Cash Out Tk1,500", "fee": 27.5}

            # The row must physically live in PostgreSQL with the expected
            # column types (a SQLite backend would not answer this).
            # `raw_data` is created as `sa.JSON()` -> PostgreSQL `json`.
            column_types = fresh.execute(
                text(
                    "SELECT pg_typeof(amount)::text AS amount_type, "
                    "pg_typeof(date)::text AS date_type, "
                    "pg_typeof(raw_data)::text AS raw_data_type "
                    "FROM transactions WHERE id = :id"
                ),
                {"id": transaction_id},
            ).mappings().one()

            assert column_types["amount_type"] == "numeric"
            assert column_types["date_type"] == "date"
            assert column_types["raw_data_type"] == "json"

        finally:
            fresh.close()

    finally:
        db.close()
        cleanup()


def test_transactions_are_isolated_between_users():
    """One user's transactions must never leak into another user's results."""
    cleanup()

    db = SessionLocal()

    try:
        user_a = create_user(db, USER_A_EMAIL, "Isolation User A")
        user_b = create_user(db, USER_B_EMAIL, "Isolation User B")

        create_transactions(
            db,
            [
                Transaction(
                    user_id=user_a.id,
                    trx_id=TX_A_FOOD,
                    date=date(2026, 10, 1),
                    description="Foodpanda order",
                    merchant="Foodpanda",
                    amount=Decimal("-850.00"),
                    category="Food",
                ),
                Transaction(
                    user_id=user_a.id,
                    trx_id=TX_A_SALARY,
                    date=date(2026, 10, 2),
                    description="Salary",
                    merchant="Company",
                    amount=Decimal("50000.00"),
                    category="Income",
                ),
                Transaction(
                    user_id=user_b.id,
                    trx_id=TX_B_FOOD,
                    date=date(2026, 10, 1),
                    description="Foodpanda order",
                    merchant="Foodpanda",
                    amount=Decimal("-1200.00"),
                    category="Food",
                ),
            ],
        )

        rows_a = list_transactions(db, user_id=user_a.id)
        rows_b = list_transactions(db, user_id=user_b.id)

        # Each user only sees their own rows.
        assert len(rows_a) == 2
        assert len(rows_b) == 1
        assert all(row.user_id == user_a.id for row in rows_a)
        assert all(row.user_id == user_b.id for row in rows_b)
        assert {row.id for row in rows_a}.isdisjoint({row.id for row in rows_b})
        assert {row.trx_id for row in rows_a} == {TX_A_FOOD, TX_A_SALARY}
        assert {row.trx_id for row in rows_b} == {TX_B_FOOD}

        # Same merchant for both users -- the search must still be user-scoped.
        search_a = search_transactions(db, user_id=user_a.id, q="Foodpanda")
        search_b = search_transactions(db, user_id=user_b.id, q="Foodpanda")

        assert len(search_a) == 1
        assert search_a[0].user_id == user_a.id
        assert search_a[0].amount == Decimal("-850.00")
        assert len(search_b) == 1
        assert search_b[0].user_id == user_b.id
        assert search_b[0].amount == Decimal("-1200.00")

        # A user-scoped query must never reach another user's row, even when
        # the exact identifier of that row is known.
        leaked = db.execute(
            select(Transaction).where(
                Transaction.user_id == user_a.id,
                Transaction.trx_id == TX_B_FOOD,
            )
        ).scalars().all()

        assert leaked == []

        # Deleting one user must remove only that user's rows.
        db.delete(user_a)
        db.commit()

        remaining = db.execute(
            select(Transaction).where(
                Transaction.trx_id.in_([TX_A_FOOD, TX_A_SALARY, TX_B_FOOD])
            )
        ).scalars().all()

        assert len(remaining) == 1
        assert remaining[0].trx_id == TX_B_FOOD
        assert remaining[0].user_id == user_b.id

    finally:
        db.close()
        cleanup()
