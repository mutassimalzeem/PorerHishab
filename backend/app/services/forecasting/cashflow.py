from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.transactions import Transaction
from app.repositories.transaction_repository import list_transactions_in_range

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")
BANGLADESH_TIMEZONE = ZoneInfo("Asia/Dhaka")


def _q(value: Decimal) -> Decimal:
    """Round money consistently to two decimal places."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1

    return year, month + 1


def _previous_or_equal_months(start: date, end: date) -> list[str]:
    """Return every calendar month from start through end, inclusively."""
    year, month = start.year, start.month
    end_key = _month_key(end)
    months: list[str] = []

    while True:
        key = f"{year:04d}-{month:02d}"
        months.append(key)

        if key == end_key:
            break

        year, month = _next_month(year, month)

    return months


def _first_day_of_month(year: int, month: int) -> date:
    return date(year, month, 1)


def _next_month_start(value: date) -> date:
    year, month = _next_month(value.year, value.month)
    return _first_day_of_month(year, month)


def _forecast_date() -> date:
    """Use Bangladesh's calendar date for this Bangladesh-first product."""
    return datetime.now(BANGLADESH_TIMEZONE).date()


def _empty_result(
    starting_balance: Decimal,
    months_ahead: int,
    as_of_date: date,
) -> dict:
    next_month = _next_month_start(as_of_date)

    return {
        "starting_balance": _q(starting_balance),
        "forecast_anchor_date": as_of_date,
        "history_start_month": None,
        "history_end_month": None,
        "historical_months_count": 0,
        "months_with_activity": 0,
        "average_monthly_income": ZERO,
        "average_monthly_expenses": ZERO,
        "average_monthly_net": ZERO,
        "months_ahead": months_ahead,
        "forecast_start_month": _month_key(next_month),
        "projected_months": [],
        "cash_depletion_date": None,
        "status": "insufficient_data",
        "assumptions": [
            "Income is represented by positive transaction amounts.",
            "Expenses are represented by negative transaction amounts.",
            "No projection is generated without non-zero historical activity.",
            "The starting balance is supplied by the caller and is not reconciled against account balances.",
        ],
    }


def calculate_cashflow_forecast(
    transactions: list[Transaction],
    starting_balance: Decimal,
    months_ahead: int = 3,
    as_of_date: date | None = None,
) -> dict:
    """
    Calculate a deterministic monthly cashflow projection.

    Only transactions dated on or before as_of_date are considered.
    Missing months between the first and last usable transaction months
    are included as zero-activity months in the historical averages.

    The projection begins in the calendar month after as_of_date.
    A depletion date means the first projected month's first day for
    which the projected ENDING balance is <= 0; it is not an exact
    day-of-depletion estimate.
    """
    if months_ahead < 1:
        raise ValueError("months_ahead must be >= 1")

    if as_of_date is None:
        as_of_date = _forecast_date()

    if not isinstance(starting_balance, Decimal):
        starting_balance = Decimal(str(starting_balance))

    usable_transactions = [
        transaction
        for transaction in transactions
        if transaction.date <= as_of_date
        and transaction.amount != 0
    ]

    if not usable_transactions:
        return _empty_result(
            starting_balance=starting_balance,
            months_ahead=months_ahead,
            as_of_date=as_of_date,
        )

    first_transaction_date = min(
        transaction.date for transaction in usable_transactions
    )
    last_transaction_date = max(
        transaction.date for transaction in usable_transactions
    )

    history_months = _previous_or_equal_months(
        first_transaction_date,
        last_transaction_date,
    )

    monthly_income = {month: Decimal("0") for month in history_months}
    monthly_expenses = {month: Decimal("0") for month in history_months}
    active_months: set[str] = set()

    for transaction in usable_transactions:
        month = _month_key(transaction.date)
        active_months.add(month)

        if transaction.amount > 0:
            monthly_income[month] += transaction.amount
        else:
            monthly_expenses[month] += abs(transaction.amount)

    month_count = Decimal(len(history_months))

    average_income = _q(
        sum(monthly_income.values(), Decimal("0")) / month_count
    )
    average_expenses = _q(
        sum(monthly_expenses.values(), Decimal("0")) / month_count
    )

    # Derive net from the rounded monetary values so the displayed
    # baseline is consistent with each month's projected net.
    average_net = _q(average_income - average_expenses)

    projected_months: list[dict] = []
    current_balance = _q(starting_balance)
    depletion_date: date | None = None

    projection_month = _next_month_start(as_of_date)

    for _ in range(months_ahead):
        projected_net = _q(average_income - average_expenses)
        current_balance = _q(current_balance + projected_net)

        projected_months.append(
            {
                "month": _month_key(projection_month),
                "projected_income": average_income,
                "projected_expenses": average_expenses,
                "projected_net": projected_net,
                "projected_balance": current_balance,
            }
        )

        if current_balance <= 0 and depletion_date is None:
            depletion_date = projection_month

        projection_month = _first_day_of_month(
            *_next_month(
                projection_month.year,
                projection_month.month,
            )
        )

    if average_net > 0:
        status = "healthy"
    elif average_net == 0:
        status = "break_even"
    else:
        status = "at_risk"

    return {
        "starting_balance": _q(starting_balance),
        "forecast_anchor_date": as_of_date,
        "history_start_month": history_months[0],
        "history_end_month": history_months[-1],
        "historical_months_count": len(history_months),
        "months_with_activity": len(active_months),
        "average_monthly_income": average_income,
        "average_monthly_expenses": average_expenses,
        "average_monthly_net": average_net,
        "months_ahead": months_ahead,
        "forecast_start_month": _month_key(_next_month_start(as_of_date)),
        "projected_months": projected_months,
        "cash_depletion_date": depletion_date,
        "status": status,
        "assumptions": [
            "Income is represented by positive transaction amounts.",
            "Expenses are represented by negative transaction amounts.",
            "Missing calendar months between the first and last usable transaction months count as zero activity.",
            "Historical monthly averages are simple averages, not seasonal or trend-adjusted forecasts.",
            "The projection starts in the month after the forecast anchor date.",
            "The starting balance is supplied by the caller and is not reconciled against account balances.",
            "Cash depletion is reported at month-level resolution using the projected ending balance.",
            "The status describes average net cashflow and does not establish that discretionary spending is safe.",
        ],
    }


def get_user_cashflow_forecast(
    db: Session,
    user_id: int,
    starting_balance: Decimal,
    months_ahead: int = 3,
) -> dict:
    """Load only the authenticated user's transactions and forecast them."""
    transactions = list_transactions_in_range(db, user_id)

    return calculate_cashflow_forecast(
        transactions=transactions,
        starting_balance=starting_balance,
        months_ahead=months_ahead,
    )
