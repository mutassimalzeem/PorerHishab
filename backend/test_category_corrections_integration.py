from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.core.database import SessionLocal
from app.models import Transaction, User
from app.models.category_correction import TransactionCategoryCorrection


RUN_ID = uuid4().hex
TEST_EMAIL = f"category-correction-{RUN_ID}@zyra.local"


def cleanup():
    db = SessionLocal()

    try:
        db.execute(
            User.__table__.delete().where(
                User.__table__.c.email == TEST_EMAIL
            )
        )
        db.commit()
    finally:
        db.close()


def test_category_correction_round_trip():
    cleanup()

    db = SessionLocal()

    try:
        user = User(
            email=TEST_EMAIL,
            hashed_password="test-password",
            full_name="Category Test User",
        )

        db.add(user)
        db.flush()

        transaction = Transaction(
            user_id=user.id,
            trx_id=f"CORRECTION-{RUN_ID}",
            date=date(2026, 10, 10),
            description="Food delivery",
            merchant="Foodpanda",
            amount=Decimal("-850.00"),
            fee=Decimal("0.00"),
            transaction_type="expense",
            category="Food",
            category_confidence=Decimal("0.950"),
            category_method="rule",
            category_reason="Matched Foodpanda merchant rule.",
            source="manual",
        )

        db.add(transaction)
        db.flush()

        correction = TransactionCategoryCorrection(
            user_id=user.id,
            transaction_id=transaction.id,
            old_category=transaction.category,
            new_category="Business",
            old_method=transaction.category_method,
        )

        transaction.category = "Business"
        transaction.category_confidence = Decimal("1.000")
        transaction.category_method = "user"
        transaction.category_reason = (
            "User changed category from 'Food' to 'Business'."
        )

        db.add(correction)
        db.commit()

        db.refresh(transaction)
        db.refresh(correction)

        assert transaction.category == "Business"
        assert transaction.category_method == "user"
        assert transaction.category_confidence == Decimal("1.000")

        assert correction.user_id == user.id
        assert correction.transaction_id == transaction.id
        assert correction.old_category == "Food"
        assert correction.new_category == "Business"
        assert correction.old_method == "rule"

    finally:
        cleanup()
        db.close()