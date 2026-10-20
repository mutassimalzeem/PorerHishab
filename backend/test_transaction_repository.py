from app.core.database import SessionLocal
from app.models import User
from app.repositories.transaction_repository import (
    create_transactions,
    list_transactions,
    search_transactions,
)
from app.models.transactions import Transaction


TEST_EMAIL_1 = "repository-test-1@zyra.local"
TEST_EMAIL_2 = "repository-test-2@zyra.local"


def cleanup():
    db = SessionLocal()

    try:
        users = (
            db.query(User)
            .filter(
                User.email.in_(
                    [TEST_EMAIL_1, TEST_EMAIL_2]
                )
            )
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
            full_name="Repository Test User",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user
    finally:
        db.close()


def test_create_and_list_transactions():
    cleanup()

    try:
        user = create_user(TEST_EMAIL_1)

        db = SessionLocal()

        try:
            transactions = [
                Transaction(
                    user_id=user.id,
                    date="2026-10-01",
                    description="Foodpanda order",
                    merchant="Foodpanda",
                    amount=-850,
                    category="Food",
                ),
                Transaction(
                    user_id=user.id,
                    date="2026-10-02",
                    description="Salary",
                    merchant="Company",
                    amount=50000,
                    category="Income",
                ),
            ]

            create_transactions(db, transactions)

            rows = list_transactions(
                db=db,
                user_id=user.id,
            )

            assert len(rows) == 2
            assert rows[0].merchant == "Company"
            assert rows[1].merchant == "Foodpanda"

        finally:
            db.close()

    finally:
        cleanup()


def test_search_is_scoped_to_user():
    cleanup()

    try:
        user1 = create_user(TEST_EMAIL_1)
        user2 = create_user(TEST_EMAIL_2)

        db = SessionLocal()

        try:
            create_transactions(
                db,
                [
                    Transaction(
                        user_id=user1.id,
                        date="2026-10-01",
                        description="Foodpanda order",
                        merchant="Foodpanda",
                        amount=-850,
                        category="Food",
                    ),
                    Transaction(
                        user_id=user2.id,
                        date="2026-10-01",
                        description="Foodpanda order",
                        merchant="Foodpanda",
                        amount=-1200,
                        category="Food",
                    ),
                ],
            )

            rows = search_transactions(
                db=db,
                user_id=user1.id,
                q="Foodpanda",
            )

            assert len(rows) == 1
            assert rows[0].amount == -850
            assert rows[0].user_id == user1.id

        finally:
            db.close()

    finally:
        cleanup()