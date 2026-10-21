from datetime import date
from decimal import Decimal

from app.models.transactions import Transaction
from app.services.planning import calculate_savings_plan


def tx(amount: str, day: date, category: str = "Food") -> Transaction:

    return Transaction(
        date=day,
        amount=Decimal(amount),
        category=category)


def test_savings_plan_on_track():

    transactions = [
        tx("50000", date(2026, 7, 1)),
        tx("-30000", date(2026, 7, 15), "Food"),

        tx("50000", date(2026, 8, 1)),
        tx("-30000", date(2026, 8, 15), "Food"),

        tx("50000", date(2026, 9, 1)),
        tx("-30000", date(2026, 9, 15), "Food"),
    ]

    result = calculate_savings_plan(
        transactions=transactions,
        goal_amount=Decimal("60000"),
        current_saved=Decimal("0"),
        target_date=date(2026, 12, 31),
        today=date(2026, 10, 1),
    )

    assert result["remaining_goal"] == Decimal("60000.00")
    assert result["months_remaining"] == 3
    assert result["required_monthly_saving"] == Decimal("20000.00")

    assert result["estimated_monthly_income"] == Decimal("50000.00")
    assert result["estimated_monthly_spending"] == Decimal("30000.00")

    assert result["estimated_monthly_surplus"] == Decimal("20000.00")

    assert result["status"] == "on_track"
    assert result["recommended_monthly_cut"] == Decimal("0.00")


def test_savings_plan_at_risk():

    transactions = [
        tx("50000", date(2026, 7, 1)),
        tx("-45000", date(2026, 7, 15), "Food"),

        tx("50000", date(2026, 8, 1)),
        tx("-45000", date(2026, 8, 15), "Food"),

        tx("50000", date(2026, 9, 1)),
        tx("-45000", date(2026, 9, 15), "Food"),
    ]

    result = calculate_savings_plan(
        transactions=transactions,
        goal_amount=Decimal("60000"),
        current_saved=Decimal("0"),
        target_date=date(2026, 12, 31),
        today=date(2026, 10, 1),
    )

    assert result["required_monthly_saving"] == Decimal("20000.00")
    assert result["estimated_monthly_surplus"] == Decimal("5000.00")

    assert result["status"] == "at_risk"

    assert result["recommended_monthly_cut"] > Decimal("0.00")
    assert len(result["recommendations"]) > 0


def test_savings_plan_with_existing_savings():

    transactions = [
        tx("50000", date(2026, 9, 1)),
        tx("-30000", date(2026, 9, 15), "Food"),
    ]

    result = calculate_savings_plan(
        transactions=transactions,
        goal_amount=Decimal("60000"),
        current_saved=Decimal("40000"),
        target_date=date(2026, 12, 31),
        today=date(2026, 10, 1),
    )

    assert result["remaining_goal"] == Decimal("20000.00")
    assert result["months_remaining"] == 3
    assert result["required_monthly_saving"] == Decimal("6666.67")


def test_completed_goal():

    result = calculate_savings_plan(
        transactions=[],
        goal_amount=Decimal("50000"),
        current_saved=Decimal("50000"),
        target_date=date(2026, 12, 31),
        today=date(2026, 10, 1),
    )

    assert result["remaining_goal"] == Decimal("0.00")
    assert result["required_monthly_saving"] == Decimal("0.00")
    assert result["status"] == "complete"


def test_invalid_goal():

    try:
        calculate_savings_plan(
            transactions=[],
            goal_amount=Decimal("0"),
            current_saved=Decimal("0"),
            target_date=date(2026, 12, 31),
            today=date(2026, 10, 1),
        )
        assert False
    except ValueError as exc:
        assert "goal_amount" in str(exc)