"""Transaction intelligence engine.

Pure calculation layer for Zyra's finance insights.  Every function in this
module takes plain :class:`~app.models.transactions.Transaction` rows (or
anything exposing the same attributes) and returns ``Decimal``-based results —
no floating point money math anywhere.

Sign convention (matches the rest of the codebase):

* ``amount > 0``  → income
* ``amount < 0``  → expense

The DB-facing entry points (:func:`get_user_insights` and friends) pull the
user's transactions through the repository layer, keeping the flow::

    FastAPI -> analytics service -> repository -> SQLAlchemy -> PostgreSQL
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import groupby
from statistics import median
from typing import Iterable, Sequence

from sqlalchemy.orm import Session

from app.models.transactions import Transaction
from app.repositories.transaction_repository import list_transactions_in_range

# Money is stored as NUMERIC(14, 2); rates get a little more precision.
TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")

DEFAULT_TOP_MERCHANTS = 5
DEFAULT_RECURRING_MIN_OCCURRENCES = 3
DEFAULT_RECURRING_TOLERANCE = Decimal("0.10")  # ±10 % around the median amount

UNCATEGORIZED = "Uncategorized"


def _q(value: Decimal, places: Decimal = TWO_PLACES) -> Decimal:
    """Quantize to a fixed number of decimal places (banker's rounding)."""
    return value.quantize(places, rounding=ROUND_HALF_EVEN)


def _sum(values: Iterable[Decimal]) -> Decimal:
    return sum(values, Decimal("0"))


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _merchant_label(transaction: Transaction) -> str:
    """Best human-readable merchant name, falling back sensibly."""
    for candidate in (
        transaction.normalized_merchant,
        transaction.merchant,
        transaction.description,
    ):
        if candidate and candidate.strip():
            return candidate.strip()

    return "Unknown"


def _merchant_key(transaction: Transaction) -> str:
    """Grouping key for merchant-based analytics (recurring, top merchants)."""
    return _merchant_label(transaction).lower()


# ---------------------------------------------------------------------------
# Core metrics
# ---------------------------------------------------------------------------


def compute_savings_rate(income: Decimal, expenses: Decimal) -> Decimal | None:
    """``(income + expenses) / income`` — ``None`` when there is no income.

    ``expenses`` is negative by the sign convention, so a user who earned
    50,000 and spent 40,000 gets ``0.2000``.
    """
    if income <= 0:
        return None

    return _q((income + expenses) / income, FOUR_PLACES)


def compute_summary(transactions: Sequence[Transaction]) -> dict:
    """Income vs expense totals, net position, and savings rate."""
    income = _sum(t.amount for t in transactions if t.amount > 0)
    expenses = _sum(t.amount for t in transactions if t.amount < 0)

    return {
        "transaction_count": len(transactions),
        "total_income": _q(income),
        "total_expenses": _q(expenses),
        "net": _q(income + expenses),
        "savings_rate": compute_savings_rate(income, expenses),
    }


def compute_monthly_breakdown(transactions: Sequence[Transaction]) -> list[dict]:
    """Income / expenses / net grouped by ``YYYY-MM``, oldest month first."""
    buckets: dict[str, dict[str, Decimal]] = {}

    for transaction in transactions:
        month = _month_key(transaction.date)
        bucket = buckets.setdefault(
            month, {"income": Decimal("0"), "expenses": Decimal("0")}
        )

        if transaction.amount > 0:
            bucket["income"] += transaction.amount
        elif transaction.amount < 0:
            bucket["expenses"] += transaction.amount

    return [
        {
            "month": month,
            "income": _q(bucket["income"]),
            "expenses": _q(bucket["expenses"]),
            "net": _q(bucket["income"] + bucket["expenses"]),
        }
        for month, bucket in sorted(buckets.items())
    ]


def compute_category_breakdown(transactions: Sequence[Transaction]) -> dict:
    """Income, expenses, and net grouped by category (``None`` → Uncategorized)."""
    income_by: dict[str, Decimal] = {}
    expenses_by: dict[str, Decimal] = {}
    net_by: dict[str, Decimal] = {}

    for transaction in transactions:
        category = transaction.category or UNCATEGORIZED

        income_by[category] = income_by.get(category, Decimal("0"))
        expenses_by[category] = expenses_by.get(category, Decimal("0"))
        net_by[category] = net_by.get(category, Decimal("0"))

        if transaction.amount > 0:
            income_by[category] += transaction.amount
        elif transaction.amount < 0:
            expenses_by[category] += transaction.amount

        net_by[category] += transaction.amount

    grand_income = _sum(income_by.values())
    grand_expenses = _sum(expenses_by.values())

    return {
        "income_by_category": {k: _q(v) for k, v in sorted(income_by.items())},
        "expenses_by_category": {k: _q(v) for k, v in sorted(expenses_by.items())},
        "net_by_category": {k: _q(v) for k, v in sorted(net_by.items())},
        "grand_totals": {
            "income": _q(grand_income),
            "expenses": _q(grand_expenses),
            "net": _q(grand_income + grand_expenses),
        },
    }


def compute_top_merchants(
    transactions: Sequence[Transaction],
    limit: int = DEFAULT_TOP_MERCHANTS,
) -> list[dict]:
    """Where the money goes: merchants ranked by total spending (magnitude)."""
    totals: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}

    for transaction in transactions:
        if transaction.amount >= 0:
            continue

        key = _merchant_key(transaction)
        labels.setdefault(key, _merchant_label(transaction))
        totals[key] = totals.get(key, Decimal("0")) + transaction.amount
        counts[key] = counts.get(key, 0) + 1

    ranked = sorted(
        totals.items(),
        key=lambda item: (item[1], item[0]),  # most negative first, then name
    )[: max(0, int(limit))]

    return [
        {
            "merchant": labels[key],
            "total_spent": _q(abs(total)),
            "transaction_count": counts[key],
        }
        for key, total in ranked
    ]


# ---------------------------------------------------------------------------
# Recurring transaction detection
# ---------------------------------------------------------------------------


def detect_recurring_transactions(
    transactions: Sequence[Transaction],
    min_occurrences: int = DEFAULT_RECURRING_MIN_OCCURRENCES,
    tolerance: Decimal = DEFAULT_RECURRING_TOLERANCE,
) -> list[dict]:
    """Heuristic recurring-charge detection for expenses.

    A merchant counts as recurring when at least ``min_occurrences``
    transactions share a similar amount (within ``tolerance`` of the group's
    median) and those transactions span at least two distinct months.  This
    catches monthly bills and subscriptions while ignoring one-off splurges
    at the same merchant and same-month repeat purchases.
    """
    groups: dict[str, list[Transaction]] = {}

    for transaction in transactions:
        if transaction.amount >= 0:
            continue

        key = _merchant_key(transaction)

        if key == "unknown":
            continue

        groups.setdefault(key, []).append(transaction)

    results: list[dict] = []

    for key, rows in groups.items():
        if len(rows) < min_occurrences:
            continue

        amounts = [abs(row.amount) for row in rows]
        median_amount = median(amounts)

        low = median_amount * (Decimal("1") - tolerance)
        high = median_amount * (Decimal("1") + tolerance)

        similar = [
            row
            for row, amount in zip(rows, amounts)
            if low <= amount <= high
        ]

        if len(similar) < min_occurrences:
            continue

        months = {_month_key(row.date) for row in similar}

        if len(months) < 2:
            continue

        results.append(
            {
                "merchant": _merchant_label(similar[0]),
                "occurrences": len(similar),
                "months": len(months),
                "median_amount": _q(median_amount),
                "total_spent": _q(_sum(abs(row.amount) for row in similar)),
                "first_date": min(row.date for row in similar),
                "last_date": max(row.date for row in similar),
            }
        )

    results.sort(key=lambda item: item["total_spent"], reverse=True)

    return results


# ---------------------------------------------------------------------------
# Cash-flow timeline & budget baseline
# ---------------------------------------------------------------------------


def compute_cashflow_timeline(transactions: Sequence[Transaction]) -> list[dict]:
    """Day-by-day cash flow with a running balance, oldest day first."""
    ordered = sorted(
        transactions,
        key=lambda t: (t.date, t.id if t.id is not None else 0),
    )

    running_balance = Decimal("0")
    timeline: list[dict] = []

    for day, day_rows in groupby(ordered, key=lambda t: t.date):
        rows = list(day_rows)

        income = _sum(row.amount for row in rows if row.amount > 0)
        expenses = _sum(row.amount for row in rows if row.amount < 0)
        net = income + expenses
        running_balance += net

        timeline.append(
            {
                "date": day,
                "income": _q(income),
                "expenses": _q(expenses),
                "net": _q(net),
                "running_balance": _q(running_balance),
            }
        )

    return timeline


def compute_budget_baseline(transactions: Sequence[Transaction]) -> dict:
    """Average monthly spending, overall and per category.

    The average is taken over the months in which spending was actually
    observed for that slice, so a category used in only one month is not
    silently diluted across the whole period.
    """
    months_with_expenses = {
        _month_key(t.date) for t in transactions if t.amount < 0
    }

    if not months_with_expenses:
        return {
            "months_observed": 0,
            "monthly_total_baseline": _q(Decimal("0")),
            "categories": [],
        }

    total_expenses = _sum(t.amount for t in transactions if t.amount < 0)

    category_totals: dict[str, Decimal] = {}
    category_months: dict[str, set[str]] = {}

    for transaction in transactions:
        if transaction.amount >= 0:
            continue

        category = transaction.category or UNCATEGORIZED
        category_totals[category] = (
            category_totals.get(category, Decimal("0")) + transaction.amount
        )
        category_months.setdefault(category, set()).add(
            _month_key(transaction.date)
        )

    categories = [
        {
            "category": category,
            "monthly_average": _q(
                abs(category_totals[category]) / len(category_months[category])
            ),
            "months_observed": len(category_months[category]),
        }
        for category in sorted(
            category_totals,
            key=lambda c: abs(category_totals[c]),
            reverse=True,
        )
    ]

    return {
        "months_observed": len(months_with_expenses),
        "monthly_total_baseline": _q(
            abs(total_expenses) / len(months_with_expenses)
        ),
        "categories": categories,
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def compute_insights(
    transactions: Sequence[Transaction],
    top_merchants_limit: int = DEFAULT_TOP_MERCHANTS,
) -> dict:
    """All intelligence metrics for one set of transactions."""
    return {
        "summary": compute_summary(transactions),
        "monthly": compute_monthly_breakdown(transactions),
        "categories": compute_category_breakdown(transactions),
        "top_merchants": compute_top_merchants(
            transactions, limit=top_merchants_limit
        ),
        "recurring": detect_recurring_transactions(transactions),
        "cashflow": compute_cashflow_timeline(transactions),
        "budget_baseline": compute_budget_baseline(transactions),
    }


# ---------------------------------------------------------------------------
# DB-facing entry points (service -> repository -> database)
# ---------------------------------------------------------------------------


def _user_transactions(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Transaction]:
    return list_transactions_in_range(
        db,
        user_id,
        start_date=start_date,
        end_date=end_date,
    )


def get_user_insights(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    top_merchants_limit: int = DEFAULT_TOP_MERCHANTS,
) -> dict:
    transactions = _user_transactions(db, user_id, start_date, end_date)

    return compute_insights(transactions, top_merchants_limit)


def get_user_summary(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    return compute_summary(_user_transactions(db, user_id, start_date, end_date))


def get_user_monthly(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    return compute_monthly_breakdown(
        _user_transactions(db, user_id, start_date, end_date)
    )


def get_user_categories(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    return compute_category_breakdown(
        _user_transactions(db, user_id, start_date, end_date)
    )


def get_user_top_merchants(
    db: Session,
    user_id: int,
    limit: int = DEFAULT_TOP_MERCHANTS,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    return compute_top_merchants(
        _user_transactions(db, user_id, start_date, end_date),
        limit=limit,
    )


def get_user_recurring(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    return detect_recurring_transactions(
        _user_transactions(db, user_id, start_date, end_date)
    )


def get_user_cashflow(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    return compute_cashflow_timeline(
        _user_transactions(db, user_id, start_date, end_date)
    )


def get_user_budget_baseline(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    return compute_budget_baseline(
        _user_transactions(db, user_id, start_date, end_date)
    )
