from datetime import date
from decimal import Decimal

from app.models.transactions import Transaction
from app.services.forecasting import (
    forecast_monthly_spending,
    forecast_category_spending,
)


def tx(
    amount: str,
    day: date,
    category: str = "Food",
) -> Transaction:
    return Transaction(
        date=day,
        amount=Decimal(amount),
        category=category,
    )


def test_forecast_uses_recent_spending():

    transactions = [
        tx("-10000", date(2026, 7, 1)),
        tx("-12000", date(2026, 8, 1)),
        tx("-14000", date(2026, 9, 1)),
    ]

    result = forecast_monthly_spending(
        transactions
    )

    assert result["months_observed"] == 3

    # Historical average = 12,000
    assert result["historical_average"] == Decimal("12000.00")

    # Recent average = 12,000
    assert result["recent_average"] == Decimal("12000.00")

    assert result["forecast"] == Decimal("12000.00")
    assert result["confidence"] == "medium"


def test_forecast_with_two_months():

    transactions = [
        tx("-10000", date(2026, 8, 1)),
        tx("-14000", date(2026, 9, 1)),
    ]

    result = forecast_monthly_spending(
        transactions
    )

    assert result["forecast"] == Decimal("12000.00")
    assert result["confidence"] == "low"


def test_forecast_ignores_income():

    transactions = [
        tx("50000", date(2026, 9, 1)),
        tx("-10000", date(2026, 9, 2)),
    ]

    result = forecast_monthly_spending(
        transactions
    )

    assert result["forecast"] == Decimal("10000.00")


def test_category_forecast_uses_monthly_totals():

    transactions = [
        tx("-1000", date(2026, 7, 1), "Food"),
        tx("-2000", date(2026, 7, 15), "Food"),

        tx("-3000", date(2026, 8, 1), "Food"),

        tx("-4000", date(2026, 9, 1), "Food"),

        tx("-5000", date(2026, 9, 1), "Housing"),
    ]

    result = forecast_category_spending(
        transactions
    )

    assert result[0]["category"] == "Food"
    assert result[0]["forecast"] == Decimal("3333.33")

    assert result[1]["category"] == "Housing"
    assert result[1]["forecast"] == Decimal("1666.67")


def test_empty_forecast():

    result = forecast_monthly_spending([])

    assert result["forecast"] == Decimal("0.00")
    assert result["confidence"] == "low"