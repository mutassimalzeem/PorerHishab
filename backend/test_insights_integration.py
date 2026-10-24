"""PostgreSQL integration test for the transaction intelligence service.

Exercises the full stack::

    analytics service -> repository -> SQLAlchemy -> PostgreSQL -> back

with deterministic seed data spanning three months.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.core.database import SessionLocal
from app.models import Transaction, User
from app.services.analytics import get_user_insights

_RUN_ID = uuid4().hex
USER_EMAIL = f"insights-integration-{_RUN_ID}@porer-hishab.local"
OTHER_EMAIL = f"insights-integration-other-{_RUN_ID}@porer-hishab.local"


def cleanup() -> None:
    db = SessionLocal()

    try:
        db.execute(
            User.__table__.delete().where(
                User.__table__.c.email.in_([USER_EMAIL, OTHER_EMAIL])
            )
        )
        db.commit()
    finally:
        db.close()


def create_user(db, email: str) -> User:
    user = User(
        email=email,
        hashed_password="test-password",
        full_name="Insights Integration",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def seed_transactions(db, user_id: int) -> None:
    """Three months of salary + Netflix + Foodpanda, plus a one-off laptop."""
    rows = []

    for month in (7, 8, 9):
        rows.append(
            Transaction(
                user_id=user_id,
                trx_id=f"SAL-{_RUN_ID}-{month}",
                date=date(2026, month, 1),
                description="Monthly salary",
                merchant="Acme Corp",
                amount=Decimal("50000.00"),
                category="Income",
            )
        )
        rows.append(
            Transaction(
                user_id=user_id,
                trx_id=f"NFLX-{_RUN_ID}-{month}",
                date=date(2026, month, 5),
                description="Netflix subscription",
                merchant="Netflix",
                normalized_merchant="netflix",
                amount=Decimal("-500.00"),
                category="Entertainment",
            )
        )
        rows.append(
            Transaction(
                user_id=user_id,
                trx_id=f"FPD-{_RUN_ID}-{month}",
                date=date(2026, month, 10),
                description="Foodpanda order",
                merchant="Foodpanda",
                normalized_merchant="foodpanda",
                amount=Decimal("-850.00"),
                category="Food",
            )
        )

    rows.append(
        Transaction(
            user_id=user_id,
            trx_id=f"LAP-{_RUN_ID}",
            date=date(2026, 9, 15),
            description="Laptop",
            merchant="Startech",
            amount=Decimal("-80000.00"),
            category="Electronics",
        )
    )

    db.add_all(rows)
    db.commit()


def test_get_user_insights_against_postgres():
    cleanup()

    db = SessionLocal()

    try:
        user = create_user(db, USER_EMAIL)
        seed_transactions(db, user.id)

        insights = get_user_insights(db, user.id)

        # --- Summary -------------------------------------------------------
        summary = insights["summary"]

        assert summary["transaction_count"] == 10
        assert summary["total_income"] == Decimal("150000.00")
        assert summary["total_expenses"] == Decimal("-84050.00")
        assert summary["net"] == Decimal("65950.00")
        assert summary["savings_rate"] == Decimal("0.4397")

        # --- Monthly -------------------------------------------------------
        monthly = insights["monthly"]

        assert [row["month"] for row in monthly] == [
            "2026-07",
            "2026-08",
            "2026-09",
        ]
        assert monthly[0]["net"] == Decimal("48650.00")
        # September carries the laptop.
        assert monthly[2]["expenses"] == Decimal("-81350.00")

        # --- Categories ----------------------------------------------------
        categories = insights["categories"]

        assert categories["expenses_by_category"]["Electronics"] == Decimal(
            "-80000.00"
        )
        assert categories["income_by_category"]["Income"] == Decimal("150000.00")

        # --- Top merchants -------------------------------------------------
        top = insights["top_merchants"]

        assert top[0]["merchant"] == "Startech"
        assert top[0]["total_spent"] == Decimal("80000.00")

        # --- Recurring -----------------------------------------------------
        recurring = insights["recurring"]
        recurring_merchants = {row["merchant"] for row in recurring}

        assert recurring_merchants == {"netflix", "foodpanda"}

        netflix = next(row for row in recurring if row["merchant"] == "netflix")

        assert netflix["occurrences"] == 3
        assert netflix["months"] == 3
        assert netflix["median_amount"] == Decimal("500.00")

        # --- Cash flow -----------------------------------------------------
        cashflow = insights["cashflow"]

        assert len(cashflow) == 10
        assert cashflow[-1]["running_balance"] == Decimal("65950.00")

        # --- Budget baseline -----------------------------------------------
        baseline = insights["budget_baseline"]

        assert baseline["months_observed"] == 3
        assert baseline["monthly_total_baseline"] == Decimal("28016.67")

        baseline_by_category = {
            row["category"]: row for row in baseline["categories"]
        }

        assert baseline_by_category["Food"]["monthly_average"] == Decimal("850.00")
        assert baseline_by_category["Electronics"]["monthly_average"] == Decimal(
            "80000.00"
        )
        assert baseline_by_category["Electronics"]["months_observed"] == 1

    finally:
        db.close()
        cleanup()


def test_insights_are_isolated_between_users():
    """A user with no transactions sees zeros, never another user's data."""
    cleanup()

    db = SessionLocal()

    try:
        user = create_user(db, USER_EMAIL)
        other = create_user(db, OTHER_EMAIL)

        seed_transactions(db, user.id)

        empty = get_user_insights(db, other.id)

        assert empty["summary"]["transaction_count"] == 0
        assert empty["summary"]["total_income"] == Decimal("0.00")
        assert empty["summary"]["net"] == Decimal("0.00")
        assert empty["monthly"] == []
        assert empty["top_merchants"] == []
        assert empty["recurring"] == []
        assert empty["cashflow"] == []
        assert empty["budget_baseline"]["months_observed"] == 0

        # The other user's numbers remain intact.
        full = get_user_insights(db, user.id)

        assert full["summary"]["transaction_count"] == 10

    finally:
        db.close()
        cleanup()
