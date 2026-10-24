from datetime import date
from decimal import Decimal

from app.models.transactions import Transaction
from app.services.forecasting.cashflow import (
    calculate_cashflow_forecast,
)


def transaction(
    amount: str,
    transaction_date: date) -> Transaction:

    return Transaction(
        amount=Decimal(amount),
        date=transaction_date)


def test_cashflow_forecast_projects_positive_net():

    transactions = [
        transaction("50000", date(2026, 1, 10)),
        transaction("-40000", date(2026, 1, 15)),
        transaction("50000", date(2026, 2, 10)),
        transaction("-42000", date(2026, 2, 15)),
        transaction("50000", date(2026, 3, 10)),
        transaction("-41000", date(2026, 3, 15)),
    ]

    result = calculate_cashflow_forecast(
        transactions=transactions,
        starting_balance=Decimal("20000"),
        months_ahead=3,
    )

    assert result["average_monthly_income"] == Decimal("50000.00")
    assert result["average_monthly_expenses"] == Decimal("41000.00")
    assert result["average_monthly_net"] == Decimal("9000.00")
    assert result["status"] == "healthy"

    assert len(result["projected_months"]) == 3

    assert (
        result["projected_months"][0]["projected_balance"]
        == Decimal("29000.00")
    )


def test_cashflow_forecast_detects_at_risk():

    transactions = [
        transaction("40000", date(2026, 1, 10)),
        transaction("-45000", date(2026, 1, 15)),
        transaction("40000", date(2026, 2, 10)),
        transaction("-47000", date(2026, 2, 15)),
        transaction("40000", date(2026, 3, 10)),
        transaction("-46000", date(2026, 3, 15)),
    ]

    result = calculate_cashflow_forecast(
        transactions=transactions,
        starting_balance=Decimal("10000"),
        months_ahead=3,
    )

    assert result["status"] == "at_risk"
    assert result["average_monthly_net"] < 0


def test_cashflow_forecast_handles_no_transactions():

    result = calculate_cashflow_forecast(
        transactions=[],
        starting_balance=Decimal("10000"),
        months_ahead=3,
    )

    assert result["status"] == "insufficient_data"
    assert result["projected_months"] == []
    assert result["cash_depletion_date"] is None