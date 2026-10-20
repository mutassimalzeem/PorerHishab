from datetime import date
from decimal import Decimal

import pandas as pd

from app.core.database import SessionLocal
from app.models import User, Transaction
from backend.app.repositories.transaction_repository import (
    list_transactions,
    search_transactions,
)


TEST_EMAIL_1 = "db-store-test-1@zyra.local"
TEST_EMAIL_2 = "db-store-test-2@zyra.local"


def cleanup():
    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .filter(User.email.in_([TEST_EMAIL_1, TEST_EMAIL_2]))
            .all()
        )

        for user in users:
            db.delete(user)

        db.commit()
    finally:
        db.close()


def create_user(email: str) -> User:
    db = SessionLocal()
    try:
        user = User(
            email=email,
            hashed_password="test-password",
            full_name="DB Store Test User",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def test_save_and_list_transactions():
    cleanup()

    try:
        user = create_user(TEST_EMAIL_1)

        df = pd.DataFrame(
            [
                {
                    "date": "2026-10-01",
                    "description": "Foodpanda order",
                    "merchant": "Foodpanda",
                    "amount": -850.00,
                    "category": "Food",
                },
                {
                    "date": "2026-10-02",
                    "description": "Salary",
                    "merchant": "Company",
                    "amount": 50000.00,
                    "category": "Income",
                },
            ]
        )

        save_dataframe(df, user_id=user.id)

        rows = list_transactions(user_id=user.id)

        assert len(rows) == 2
        assert rows[0]["merchant"] == "Company"
        assert rows[1]["merchant"] == "Foodpanda"
        assert rows[0]["amount"] == 50000.00
        assert rows[1]["amount"] == -850.00

    finally:
        cleanup()


def test_search_is_scoped_to_user():
    cleanup()

    try:
        user1 = create_user(TEST_EMAIL_1)
        user2 = create_user(TEST_EMAIL_2)

        df1 = pd.DataFrame(
            [
                {
                    "date": "2026-10-01",
                    "description": "Foodpanda order",
                    "merchant": "Foodpanda",
                    "amount": -850.00,
                    "category": "Food",
                }
            ]
        )

        df2 = pd.DataFrame(
            [
                {
                    "date": "2026-10-01",
                    "description": "Foodpanda order",
                    "merchant": "Foodpanda",
                    "amount": -1200.00,
                    "category": "Food",
                }
            ]
        )

        save_dataframe(df1, user_id=user1.id)
        save_dataframe(df2, user_id=user2.id)

        rows = search_transactions(
            user_id=user1.id,
            q="Foodpanda",
        )

        assert len(rows) == 1
        assert rows[0]["amount"] == -850.00
        assert rows[0]["user_id"] == user1.id

    finally:
        cleanup()


def test_search_filters():
    cleanup()

    try:
        user = create_user(TEST_EMAIL_1)

        df = pd.DataFrame(
            [
                {
                    "date": "2026-10-01",
                    "description": "Food",
                    "merchant": "Foodpanda",
                    "amount": -850.00,
                    "category": "Food",
                },
                {
                    "date": "2026-10-05",
                    "description": "Transport",
                    "merchant": "Uber",
                    "amount": -500.00,
                    "category": "Transport",
                },
                {
                    "date": "2026-10-10",
                    "description": "Salary",
                    "merchant": "Company",
                    "amount": 50000.00,
                    "category": "Income",
                },
            ]
        )

        save_dataframe(df, user_id=user.id)

        rows = search_transactions(
            user_id=user.id,
            start_date="2026-10-03",
            end_date="2026-10-08",
            categories=["Transport"],
        )

        assert len(rows) == 1
        assert rows[0]["merchant"] == "Uber"

    finally:
        cleanup()