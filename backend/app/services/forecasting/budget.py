from __future__ import annotations
from datetime import date
from decimal import Decimal
from statistics import mean
from app.models.transactions import Transaction

TWO_PLACES = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES)

def _month_key(value: date) -> str:
    """This helper function converts a Python datetime.date object into a standardized
    string format of YYYY-MM. It is typically used as a key for grouping, sorting, or
    indexing data by month."""
    return f"{value.year:04d}-{value.month:02d}"


def forecast_monthly_spending(transactions: list[Transaction], months_ahead: int = 1) -> dict:
    """
    Forecast future monthly spending from historical expense data.

    V1 deliberately uses an explainable baseline:
    - historical monthly spending average
    - recent 3-month average
    - weighted combination of the two

    Expenses are stored as negative values, but the forecast is returned
    as a positive spending amount.
    """

    if months_ahead < 1:
        raise ValueError("months_ahead must be >= 1")

    expenses = [transaction for transaction in transactions if transaction.amount < 0]

    if not expenses:
        return {
            "months_ahead": months_ahead,
            "forecast": Decimal("0.00"),
            "historical_average": Decimal("0.00"),
            "recent_average": Decimal("0.00"),
            "confidence": "low",
            "months_observed": 0,
        }

    monthly_totals: dict[str, Decimal] = {}

    for transaction in expenses:
        month = _month_key(transaction.date)

        monthly_totals[month] = (
            monthly_totals.get(month, Decimal("0"))
            + abs(transaction.amount)
        )

    ordered_months = sorted(monthly_totals)

    values = [monthly_totals[month] for month in ordered_months]

    historical_average = sum(values, Decimal("0")) / len(values)

    recent_values = values[-3:]

    recent_average = sum(
        recent_values,
        Decimal("0"),
    ) / len(recent_values)

    if len(values) >= 3:
        forecast = (
            historical_average * Decimal("0.4")
            + recent_average * Decimal("0.6")
        )
        confidence = "medium"
    else:
        forecast = historical_average
        confidence = "low"

    return {
        "months_ahead": months_ahead,
        "forecast": _q(forecast),
        "historical_average": _q(historical_average),
        "recent_average": _q(recent_average),
        "confidence": confidence,
        "months_observed": len(values),
    }


def forecast_category_spending(
    transactions: list[Transaction],
) -> list[dict]:
    """
    Forecast next-month spending by category.

    Uses monthly category totals rather than individual transaction
    averages. This prevents transaction frequency from distorting
    the forecast.
    """

    monthly_category_totals: dict[str, dict[str, Decimal]] = {}

    for transaction in transactions:
        if transaction.amount >= 0:
            continue

        category = transaction.category or "Uncategorized"
        month = _month_key(transaction.date)

        if month not in monthly_category_totals:
            monthly_category_totals[month] = {}

        monthly_category_totals[month][category] = (
            monthly_category_totals[month].get(category, Decimal("0"))
            + abs(transaction.amount)
        )

    if not monthly_category_totals:
        return []

    categories = set()

    for month_data in monthly_category_totals.values():
        categories.update(month_data.keys())

    results = []

    for category in categories:
        monthly_values = [month_data.get(category, Decimal("0"))
            for month_data in monthly_category_totals.values()
        ]

        average = (sum(monthly_values, Decimal("0")) / len(monthly_values))

        observations = sum(1
            for month_data in monthly_category_totals.values()
            if category in month_data
        )

        results.append(
            {
                "category": category,
                "forecast": _q(average),
                "observations": observations,
            }
        )

    results.sort(
        key=lambda item: item["forecast"],
        reverse=True,
    )

    return results



from sqlalchemy.orm import Session

from app.repositories.transaction_repository import (
    list_transactions_in_range,
)


def get_user_budget_forecast(
    db: Session,
    user_id: int,
    months_ahead: int = 1,
) -> dict:
    transactions = list_transactions_in_range(
        db,
        user_id,
        limit=10000,
    )

    forecast = forecast_monthly_spending(
        transactions,
        months_ahead=months_ahead,
    )

    categories = forecast_category_spending(
        transactions,
    )

    forecast["categories"] = categories

    return forecast