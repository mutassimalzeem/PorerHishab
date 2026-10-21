"""Unit tests for the transaction intelligence engine.

These run without a database: the analytics functions are pure calculations
over ``Transaction`` rows, so tests construct rows directly and assert on the
``Decimal`` results.
"""

from datetime import date
from decimal import Decimal

from app.models.transactions import Transaction
from app.services.analytics import (
    compute_budget_baseline,
    compute_cashflow_timeline,
    compute_category_breakdown,
    compute_monthly_breakdown,
    compute_savings_rate,
    compute_summary,
    compute_top_merchants,
    detect_recurring_transactions,
)


def tx(
    amount: str,
    day: date,
    merchant: str | None = None,
    normalized: str | None = None,
    category: str | None = None,
    description: str | None = None,
    tx_id: int | None = None,
) -> Transaction:
    """Build an unsaved Transaction row for the pure calculation tests."""
    return Transaction(
        id=tx_id,
        date=day,
        amount=Decimal(amount),
        merchant=merchant,
        normalized_merchant=normalized,
        category=category,
        description=description,
    )


# ---------------------------------------------------------------------------
# Summary / income vs expense / savings rate
# ---------------------------------------------------------------------------


def test_summary_income_vs_expense():
    transactions = [
        tx("50000.00", date(2026, 10, 1), merchant="Acme", category="Income"),
        tx("-20000.00", date(2026, 10, 2), merchant="Rent", category="Housing"),
        tx("-5000.75", date(2026, 10, 3), merchant="Groceries", category="Food"),
    ]

    summary = compute_summary(transactions)

    assert summary["transaction_count"] == 3
    assert summary["total_income"] == Decimal("50000.00")
    assert summary["total_expenses"] == Decimal("-25000.75")
    assert summary["net"] == Decimal("24999.25")
    assert summary["savings_rate"] == Decimal("0.5000")


def test_summary_empty():
    summary = compute_summary([])

    assert summary["transaction_count"] == 0
    assert summary["total_income"] == Decimal("0.00")
    assert summary["total_expenses"] == Decimal("0.00")
    assert summary["net"] == Decimal("0.00")
    assert summary["savings_rate"] is None


def test_savings_rate_zero_income_returns_none():
    assert compute_savings_rate(Decimal("0"), Decimal("-100")) is None


def test_savings_rate_negative_net():
    # Spent more than earned -> negative savings rate.
    assert compute_savings_rate(Decimal("100"), Decimal("-150")) == Decimal("-0.5000")


# ---------------------------------------------------------------------------
# Monthly breakdown
# ---------------------------------------------------------------------------


def test_monthly_breakdown_groups_and_sorts():
    transactions = [
        tx("50000.00", date(2026, 10, 1), category="Income"),
        tx("-12000.00", date(2026, 10, 5), category="Housing"),
        tx("48000.00", date(2026, 9, 1), category="Income"),
        tx("-9000.00", date(2026, 9, 20), category="Housing"),
        tx("-100.00", date(2026, 8, 31), category="Food"),
    ]

    monthly = compute_monthly_breakdown(transactions)

    assert [row["month"] for row in monthly] == [
        "2026-08",
        "2026-09",
        "2026-10",
    ]
    assert monthly[0]["expenses"] == Decimal("-100.00")
    assert monthly[1]["income"] == Decimal("48000.00")
    assert monthly[1]["net"] == Decimal("39000.00")
    assert monthly[2]["net"] == Decimal("38000.00")


def test_monthly_breakdown_empty():
    assert compute_monthly_breakdown([]) == []


# ---------------------------------------------------------------------------
# Category breakdown
# ---------------------------------------------------------------------------


def test_category_breakdown_uncategorized_fallback():
    transactions = [
        tx("-500.00", date(2026, 10, 1), category="Food"),
        tx("-300.00", date(2026, 10, 2), category=None),
        tx("1000.00", date(2026, 10, 3), category=None),
    ]

    breakdown = compute_category_breakdown(transactions)

    assert breakdown["expenses_by_category"] == {
        "Food": Decimal("-500.00"),
        "Uncategorized": Decimal("-300.00"),
    }
    assert breakdown["income_by_category"]["Uncategorized"] == Decimal("1000.00")
    assert breakdown["net_by_category"]["Food"] == Decimal("-500.00")
    assert breakdown["grand_totals"] == {
        "income": Decimal("1000.00"),
        "expenses": Decimal("-800.00"),
        "net": Decimal("200.00"),
    }


def test_category_breakdown_empty():
    breakdown = compute_category_breakdown([])

    assert breakdown["income_by_category"] == {}
    assert breakdown["expenses_by_category"] == {}
    assert breakdown["net_by_category"] == {}
    assert breakdown["grand_totals"]["net"] == Decimal("0.00")


# ---------------------------------------------------------------------------
# Top merchants
# ---------------------------------------------------------------------------


def test_top_merchants_ranks_by_spend_and_limits():
    transactions = [
        tx("-850.00", date(2026, 10, 1), merchant="Foodpanda", normalized="foodpanda"),
        tx("-950.00", date(2026, 10, 8), merchant="Foodpanda", normalized="foodpanda"),
        tx("-5000.00", date(2026, 10, 2), merchant="Startech", normalized="startech"),
        tx("50000.00", date(2026, 10, 3), merchant="Acme", normalized="acme"),
    ]

    top = compute_top_merchants(transactions, limit=1)

    assert len(top) == 1
    assert top[0]["merchant"] == "startech"
    assert top[0]["total_spent"] == Decimal("5000.00")
    assert top[0]["transaction_count"] == 1


def test_top_merchants_falls_back_to_description_then_unknown():
    transactions = [
        tx("-100.00", date(2026, 10, 1), description="Uber ride"),
        tx("-200.00", date(2026, 10, 2)),
    ]

    top = compute_top_merchants(transactions)

    assert {row["merchant"] for row in top} == {"Uber ride", "Unknown"}


def test_top_merchants_empty():
    assert compute_top_merchants([]) == []


# ---------------------------------------------------------------------------
# Recurring detection
# ---------------------------------------------------------------------------


def test_recurring_detection_flags_monthly_subscription():
    transactions = [
        tx("-500.00", date(2026, 7, 5), merchant="Netflix", normalized="netflix"),
        tx("-500.00", date(2026, 8, 5), merchant="Netflix", normalized="netflix"),
        tx("-510.00", date(2026, 9, 5), merchant="Netflix", normalized="netflix"),
        tx("-850.00", date(2026, 9, 6), merchant="Foodpanda", normalized="foodpanda"),
    ]

    recurring = detect_recurring_transactions(transactions)

    assert len(recurring) == 1
    assert recurring[0]["merchant"] == "netflix"
    assert recurring[0]["occurrences"] == 3
    assert recurring[0]["months"] == 3
    assert recurring[0]["median_amount"] == Decimal("500.00")
    assert recurring[0]["total_spent"] == Decimal("1510.00")
    assert recurring[0]["first_date"] == date(2026, 7, 5)
    assert recurring[0]["last_date"] == date(2026, 9, 5)


def test_recurring_ignores_wildly_different_amounts():
    transactions = [
        tx("-100.00", date(2026, 7, 1), merchant="Shop", normalized="shop"),
        tx("-100.00", date(2026, 8, 1), merchant="Shop", normalized="shop"),
        tx("-5000.00", date(2026, 9, 1), merchant="Shop", normalized="shop"),
    ]

    # Only two of the three amounts are within tolerance of the median.
    assert detect_recurring_transactions(transactions) == []


def test_recurring_ignores_single_month_repeats():
    transactions = [
        tx("-500.00", date(2026, 9, 1), merchant="Grocer", normalized="grocer"),
        tx("-500.00", date(2026, 9, 8), merchant="Grocer", normalized="grocer"),
        tx("-500.00", date(2026, 9, 15), merchant="Grocer", normalized="grocer"),
        tx("-500.00", date(2026, 9, 22), merchant="Grocer", normalized="grocer"),
    ]

    # Four identical charges but all within one month: not a recurring bill.
    assert detect_recurring_transactions(transactions) == []


def test_recurring_ignores_income():
    transactions = [
        tx("50000.00", date(2026, 7, 1), merchant="Acme", normalized="acme"),
        tx("50000.00", date(2026, 8, 1), merchant="Acme", normalized="acme"),
        tx("50000.00", date(2026, 9, 1), merchant="Acme", normalized="acme"),
    ]

    assert detect_recurring_transactions(transactions) == []


# ---------------------------------------------------------------------------
# Cash-flow timeline
# ---------------------------------------------------------------------------


def test_cashflow_timeline_running_balance():
    transactions = [
        tx("1000.00", date(2026, 10, 2), tx_id=2),
        tx("-400.00", date(2026, 10, 1), tx_id=1),
        tx("-100.00", date(2026, 10, 1), tx_id=3),
    ]

    timeline = compute_cashflow_timeline(transactions)

    assert len(timeline) == 2

    first, second = timeline

    assert first["date"] == date(2026, 10, 1)
    assert first["income"] == Decimal("0.00")
    assert first["expenses"] == Decimal("-500.00")
    assert first["running_balance"] == Decimal("-500.00")

    assert second["date"] == date(2026, 10, 2)
    assert second["running_balance"] == Decimal("500.00")


def test_cashflow_timeline_empty():
    assert compute_cashflow_timeline([]) == []


# ---------------------------------------------------------------------------
# Budget baseline
# ---------------------------------------------------------------------------


def test_budget_baseline_averages_observed_months():
    transactions = [
        tx("-850.00", date(2026, 7, 10), category="Food"),
        tx("-850.00", date(2026, 8, 10), category="Food"),
        tx("-850.00", date(2026, 9, 10), category="Food"),
        tx("-6000.00", date(2026, 9, 1), category="Housing"),
        tx("50000.00", date(2026, 9, 1), category="Income"),
    ]

    baseline = compute_budget_baseline(transactions)

    assert baseline["months_observed"] == 3
    # Total expenses: 3 x 850 + 6000 = 8550 over 3 months.
    assert baseline["monthly_total_baseline"] == Decimal("2850.00")

    by_category = {row["category"]: row for row in baseline["categories"]}

    assert by_category["Food"]["monthly_average"] == Decimal("850.00")
    assert by_category["Food"]["months_observed"] == 3
    # Housing appears in a single month, so it is not diluted across three.
    assert by_category["Housing"]["monthly_average"] == Decimal("6000.00")
    assert by_category["Housing"]["months_observed"] == 1
    # Income never shows up in a spending baseline.
    assert "Income" not in by_category


def test_budget_baseline_no_expenses():
    baseline = compute_budget_baseline(
        [tx("500.00", date(2026, 10, 1), category="Income")]
    )

    assert baseline["months_observed"] == 0
    assert baseline["monthly_total_baseline"] == Decimal("0.00")
    assert baseline["categories"] == []
