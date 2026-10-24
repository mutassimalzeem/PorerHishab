from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from statistics import mean

from app.models.transactions import Transaction
from sqlalchemy.orm import Session
from app.repositories.transaction_repository import list_transactions_in_range


TWO_PLACES = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES)


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1

    return year, month + 1


def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def calculate_cashflow_forecast(
    transactions: list[Transaction],
    starting_balance: Decimal,
    months_ahead: int = 3,
) -> dict:
    """
    Project future monthly income, expenses, net cashflow and balance.

    This is deliberately deterministic.

    Income:
        positive transaction amounts

    Expenses:
        negative transaction amounts converted to positive spending

    Forecast baseline:
        average observed monthly income/expenses

    The LLM must not be used to calculate these values.
    """

    if months_ahead < 1:
        raise ValueError("months_ahead must be >= 1")

    monthly_income: dict[str, Decimal] = {}
    monthly_expenses: dict[str, Decimal] = {}

    for transaction in transactions:
        month = _month_key(transaction.date)

        if transaction.amount > 0:
            monthly_income[month] = (
                monthly_income.get(month, Decimal("0"))
                + transaction.amount
            )

        elif transaction.amount < 0:
            monthly_expenses[month] = (
                monthly_expenses.get(month, Decimal("0"))
                + abs(transaction.amount)
            )

    observed_months = sorted(
        set(monthly_income) | set(monthly_expenses)
    )

    if not observed_months:
        return {
            "starting_balance": _q(starting_balance),
            "average_monthly_income": Decimal("0.00"),
            "average_monthly_expenses": Decimal("0.00"),
            "average_monthly_net": Decimal("0.00"),
            "months_ahead": months_ahead,
            "projected_months": [],
            "cash_depletion_date": None,
            "status": "insufficient_data",
        }

    income_values = [
        monthly_income.get(month, Decimal("0"))
        for month in observed_months
    ]

    expense_values = [
        monthly_expenses.get(month, Decimal("0"))
        for month in observed_months
    ]

    average_income = (
        sum(income_values, Decimal("0"))
        / len(income_values)
    )

    average_expenses = (
        sum(expense_values, Decimal("0"))
        / len(expense_values)
    )

    average_net = average_income - average_expenses

    last_month = observed_months[-1]
    last_year, last_month_number = (
        int(last_month[:4]),
        int(last_month[5:7]),
    )

    current_balance = starting_balance
    projected_months: list[dict] = []
    depletion_date = None

    for _ in range(months_ahead):
        year, month = _next_month(
            last_year,
            last_month_number,
        )

        last_year = year
        last_month_number = month

        projected_income = _q(average_income)
        projected_expenses = _q(average_expenses)
        projected_net = _q(
            projected_income - projected_expenses
        )

        current_balance = _q(
            current_balance + projected_net
        )

        projected_months.append(
            {
                "month": f"{year:04d}-{month:02d}",
                "projected_income": projected_income,
                "projected_expenses": projected_expenses,
                "projected_net": projected_net,
                "projected_balance": current_balance,
            }
        )

        if (
            current_balance <= 0
            and depletion_date is None
        ):
            depletion_date = _month_start(year, month)

    if average_net > 0:
        status = "healthy"
    elif average_net == 0:
        status = "break_even"
    else:
        status = "at_risk"

    return {
        "starting_balance": _q(starting_balance),
        "average_monthly_income": _q(average_income),
        "average_monthly_expenses": _q(average_expenses),
        "average_monthly_net": _q(average_net),
        "months_ahead": months_ahead,
        "projected_months": projected_months,
        "cash_depletion_date": depletion_date,
        "status": status,
    }


def get_user_cashflow_forecast(db: Session, user_id : int, starting_balance: Decimal, months_ahead: int = 3) -> dict:
    transactions = list_transactions_in_range(db,  user_id)

    return calculate_cashflow_forecast(
    transactions=transactions,
    starting_balance=starting_balance,
    months_ahead=months_ahead,
)