
from datetime import date
from decimal import Decimal

from app.models.transactions import Transaction
from app.services.forecasting.cashflow import (calculate_cashflow_forecast)


def transaction(amount: str, transaction_date: date) -> Transaction:
    return Transaction(
        amount=Decimal(amount),
        date=transaction_date,
    )


def test_positive_net_flow_and_projection_anchor():
    transactions = [
        transaction("50000", date(2026, 7, 10)),
        transaction("-40000", date(2026, 7, 15)),
        transaction("50000", date(2026, 8, 10)),
        transaction("-42000", date(2026, 8, 15)),
        transaction("50000", date(2026, 9, 10)),
        transaction("-41000", date(2026, 9, 15)),
    ]

    result = calculate_cashflow_forecast(
        transactions=transactions,
        starting_balance=Decimal("20000"),
        months_ahead=3,
        as_of_date=date(2026, 10, 25),
    )

    assert result["average_monthly_income"] == Decimal("50000.00")
    assert result["average_monthly_expenses"] == Decimal("41000.00")
    assert result["average_monthly_net"] == Decimal("9000.00")
    assert result["status"] == "healthy"
    assert result["forecast_anchor_date"] == date(2026, 10, 25)
    assert result["history_start_month"] == "2026-07"
    assert result["history_end_month"] == "2026-09"
    assert result["historical_months_count"] == 3
    assert result["months_with_activity"] == 3
    assert result["forecast_start_month"] == "2026-11"

    assert [m["month"] for m in result["projected_months"]] == [
        "2026-11",
        "2026-12",
        "2027-01",
    ]
    assert result["projected_months"][0]["projected_balance"] == Decimal(
        "29000.00"
    )


def test_missing_calendar_month_counts_as_zero_activity():
    transactions = [
        transaction("30000", date(2026, 1, 10)),
        transaction("-10000", date(2026, 1, 20)),
        transaction("30000", date(2026, 3, 10)),
        transaction("-10000", date(2026, 3, 20)),
    ]

    result = calculate_cashflow_forecast(
        transactions=transactions,
        starting_balance=Decimal("10000"),
        months_ahead=1,
        as_of_date=date(2026, 4, 5),
    )

    # January, February (zero activity), and March are averaged.
    assert result["historical_months_count"] == 3
    assert result["months_with_activity"] == 2
    assert result["average_monthly_income"] == Decimal("20000.00")
    assert result["average_monthly_expenses"] == Decimal("6666.67")
    assert result["average_monthly_net"] == Decimal("13333.33")


def test_stale_history_does_not_anchor_projection_in_the_past():
    transactions = [
        transaction("50000", date(2025, 1, 10)),
        transaction("-30000", date(2025, 1, 15)),
    ]

    result = calculate_cashflow_forecast(
        transactions=transactions,
        starting_balance=Decimal("10000"),
        months_ahead=2,
        as_of_date=date(2026, 10, 25),
    )

    assert result["history_end_month"] == "2025-01"
    assert result["forecast_start_month"] == "2026-11"
    assert [m["month"] for m in result["projected_months"]] == [
        "2026-11",
        "2026-12",
    ]


def test_future_transactions_are_ignored():
    transactions = [
        transaction("50000", date(2026, 9, 10)),
        transaction("-30000", date(2026, 9, 15)),
        transaction("999999", date(2026, 12, 1)),
    ]

    result = calculate_cashflow_forecast(
        transactions=transactions,
        starting_balance=Decimal("10000"),
        months_ahead=1,
        as_of_date=date(2026, 10, 25),
    )

    assert result["average_monthly_income"] == Decimal("50000.00")
    assert result["average_monthly_expenses"] == Decimal("30000.00")
    assert result["history_end_month"] == "2026-09"


def test_negative_net_flow_and_depletion_month():
    transactions = [
        transaction("40000", date(2026, 1, 10)),
        transaction("-50000", date(2026, 1, 15)),
        transaction("40000", date(2026, 2, 10)),
        transaction("-50000", date(2026, 2, 15)),
    ]

    result = calculate_cashflow_forecast(
        transactions=transactions,
        starting_balance=Decimal("15000"),
        months_ahead=3,
        as_of_date=date(2026, 10, 25),
    )

    assert result["average_monthly_net"] == Decimal("-10000.00")
    assert result["status"] == "at_risk"

    # Starting at 15,000: the first projected month ends at 5,000;
    # the second ends at -5,000. Report its month start, not a fake
    # exact day-of-depletion.
    assert result["projected_months"][0]["projected_balance"] == Decimal(
        "5000.00"
    )
    assert result["projected_months"][1]["projected_balance"] == Decimal(
        "-5000.00"
    )
    assert result["cash_depletion_date"] == date(2026, 12, 1)


def test_break_even_status():
    transactions = [
        transaction("30000", date(2026, 5, 10)),
        transaction("-30000", date(2026, 5, 20)),
    ]

    result = calculate_cashflow_forecast(
        transactions=transactions,
        starting_balance=Decimal("1000"),
        months_ahead=1,
        as_of_date=date(2026, 6, 1),
    )

    assert result["average_monthly_net"] == Decimal("0.00")
    assert result["status"] == "break_even"
    assert result["cash_depletion_date"] is None


def test_empty_or_zero_only_history_is_insufficient():
    for transactions in (
        [],
        [transaction("0", date(2026, 1, 1))],
    ):
        result = calculate_cashflow_forecast(
            transactions=transactions,
            starting_balance=Decimal("10000"),
            months_ahead=3,
            as_of_date=date(2026, 10, 25),
        )

        assert result["status"] == "insufficient_data"
        assert result["projected_months"] == []
        assert result["cash_depletion_date"] is None
        assert result["historical_months_count"] == 0
        assert result["forecast_start_month"] == "2026-11"


def test_money_rounding_is_explicit():
    transactions = [
        transaction("1.00", date(2026, 1, 10)),
        transaction("-0.33", date(2026, 1, 15)),
        transaction("1.00", date(2026, 2, 10)),
        transaction("-0.34", date(2026, 2, 15)),
        transaction("1.00", date(2026, 3, 10)),
        transaction("-0.34", date(2026, 3, 15)),
    ]

    result = calculate_cashflow_forecast(
        transactions=transactions,
        starting_balance=Decimal("10.00"),
        months_ahead=1,
        as_of_date=date(2026, 4, 1),
    )

    assert result["average_monthly_income"] == Decimal("1.00")
    assert result["average_monthly_expenses"] == Decimal("0.34")
    assert result["average_monthly_net"] == Decimal("0.66")
    assert result["projected_months"][0]["projected_balance"] == Decimal(
        "10.66"
    )
