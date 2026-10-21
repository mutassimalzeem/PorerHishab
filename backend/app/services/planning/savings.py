from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.transactions import Transaction
from app.repositories.transaction_repository import (
    list_transactions_in_range,
)


TWO_PLACES = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES)


def _months_between(start: date, end: date) -> int:
    """
    Return the number of calendar months between two dates.

    The target month is included so a goal due later this month
    still requires a contribution for the current month.
    """

    months = ((end.year - start.year) * 12 + (end.month - start.month) + 1)

    return max(1, months)


def _monthly_totals(
    transactions: list[Transaction]) -> tuple[list[Decimal], list[Decimal]]:
    """
    Return monthly income and spending totals.
    """

    income: dict[str, Decimal] = {}
    expenses: dict[str, Decimal] = {}

    for transaction in transactions:
        month = f"{transaction.date.year:04d}-{transaction.date.month:02d}"

        if transaction.amount > 0:
            income[month] = (
                income.get(month, Decimal("0"))
                + transaction.amount
            )

        elif transaction.amount < 0:
            expenses[month] = (
                expenses.get(month, Decimal("0"))
                + abs(transaction.amount)
            )

    months = sorted(set(income) | set(expenses))

    income_values = [
        income.get(month, Decimal("0"))
        for month in months
    ]

    expense_values = [
        expenses.get(month, Decimal("0"))
        for month in months
    ]

    return income_values, expense_values


def _category_spending(
    transactions: list[Transaction],
) -> list[dict]:
    """
    Calculate average monthly spending by category.
    """

    monthly_categories: dict[str, dict[str, Decimal]] = {}

    for transaction in transactions:
        if transaction.amount >= 0:
            continue

        month = (
            f"{transaction.date.year:04d}-"
            f"{transaction.date.month:02d}"
        )

        category = transaction.category or "Uncategorized"

        monthly_categories.setdefault(month, {})

        monthly_categories[month][category] = (
            monthly_categories[month].get(
                category,
                Decimal("0"),
            )
            + abs(transaction.amount)
        )

    if not monthly_categories:
        return []

    categories = set()

    for month_data in monthly_categories.values():
        categories.update(month_data.keys())

    results = []

    for category in categories:
        values = [
            month_data.get(category, Decimal("0"))
            for month_data in monthly_categories.values()
        ]

        average = (
            sum(values, Decimal("0"))
            / len(values)
        )

        results.append(
            {
                "category": category,
                "monthly_average": _q(average),
            }
        )

    results.sort(
        key=lambda item: item["monthly_average"],
        reverse=True,
    )

    return results


def calculate_savings_plan(
    transactions: list[Transaction],
    goal_amount: Decimal,
    current_saved: Decimal,
    target_date: date,
    today: date | None = None,
) -> dict:
    """
    Build a deterministic savings plan from historical transactions.
    """

    if goal_amount <= 0:
        raise ValueError("goal_amount must be greater than zero")

    if current_saved < 0:
        raise ValueError("current_saved cannot be negative")

    if today is None:
        today = date.today()

    if target_date < today:
        raise ValueError("target_date cannot be in the past")

    remaining_goal = max(
        Decimal("0"),
        goal_amount - current_saved,
    )

    months_remaining = _months_between(
        today,
        target_date,
    )

    required_monthly_saving = (
        remaining_goal / months_remaining
    )

    income_values, expense_values = _monthly_totals(
        transactions
    )

    if income_values:
        average_monthly_income = (
            sum(income_values, Decimal("0"))
            / len(income_values)
        )
    else:
        average_monthly_income = Decimal("0")

    if expense_values:
        average_monthly_spending = (
            sum(expense_values, Decimal("0"))
            / len(expense_values)
        )
    else:
        average_monthly_spending = Decimal("0")

    estimated_surplus = (
        average_monthly_income
        - average_monthly_spending
    )

    shortfall = max(
        Decimal("0"),
        required_monthly_saving - estimated_surplus,
    )

    if required_monthly_saving == 0:
        status = "complete"
    elif estimated_surplus >= required_monthly_saving:
        status = "on_track"
    else:
        status = "at_risk"

    categories = _category_spending(transactions)

    recommendations = []

    if shortfall > 0:
        for category in categories:
            monthly_average = category["monthly_average"]

            if monthly_average <= 0:
                continue

            suggested_cut = min(
                monthly_average * Decimal("0.20"),
                shortfall,
            )

            if suggested_cut <= 0:
                continue

            recommendations.append(
                {
                    "category": category["category"],
                    "monthly_spending": monthly_average,
                    "suggested_cut": _q(suggested_cut),
                }
            )

            shortfall -= suggested_cut

            if shortfall <= 0:
                break

    recommended_cut = sum(
        (
            item["suggested_cut"]
            for item in recommendations
        ),
        Decimal("0"),
    )

    projected_monthly_saving = (
        estimated_surplus + recommended_cut
    )

    return {
        "goal_amount": _q(goal_amount),
        "current_saved": _q(current_saved),
        "remaining_goal": _q(remaining_goal),
        "target_date": target_date,
        "months_remaining": months_remaining,
        "required_monthly_saving": _q(
            required_monthly_saving
        ),
        "estimated_monthly_income": _q(
            average_monthly_income
        ),
        "estimated_monthly_spending": _q(
            average_monthly_spending
        ),
        "estimated_monthly_surplus": _q(
            estimated_surplus
        ),
        "recommended_monthly_cut": _q(
            recommended_cut
        ),
        "projected_monthly_saving": _q(
            projected_monthly_saving
        ),
        "status": status,
        "recommendations": recommendations,
    }


def get_user_savings_plan(
    db: Session,
    user_id: int,
    goal_amount: Decimal,
    current_saved: Decimal,
    target_date: date,
) -> dict:
    transactions = list_transactions_in_range(
        db,
        user_id,
        limit=10000,
    )

    return calculate_savings_plan(
        transactions=transactions,
        goal_amount=goal_amount,
        current_saved=current_saved,
        target_date=target_date,
    )