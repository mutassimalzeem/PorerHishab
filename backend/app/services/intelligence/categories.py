"""Reusable category-level spending facts and comparisons (AI-13).

Category arithmetic stays deterministic and wired to the categorization
system only through the strings the records actually carry: no category is
inferred here that the categorization system does not produce. Unknown
categories surface as the user's own uncategorized label, exactly as the
existing analytics code does.

Two kinds of numbers are kept apart:

* ``observed`` — grouped expense totals for real records;
* ``comparison``/``delta``/``percentage_change`` — derived values that are
  ``None`` whenever the baseline is zero or unknown (no fabricated
  percentages).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN

from sqlalchemy.orm import Session

from app.services.intelligence.facts import grouped_expenses
from app.services.intelligence.periods import Period, money

FOUR_PLACES = Decimal("0.0001")
PERCENT_SCALE = Decimal("0.01")
#: Ranking limit used when the engine needs every category, not a top-N page.
ALL_CATEGORIES_LIMIT = 1000


@dataclass
class CategorySpendingFact:
    """One category's spending for a period plus its comparison, if any."""

    category: str
    observed_period: Period
    observed_expenses: Decimal
    observed_transactions: int
    comparison_period: Period | None = None
    comparison_expenses: Decimal | None = None
    delta: Decimal | None = None
    percentage_change: Decimal | None = None

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "observed_period": self.observed_period.to_dict(),
            "observed_expenses": str(self.observed_expenses),
            "observed_transactions": self.observed_transactions,
            "comparison_period": None if self.comparison_period is None
            else self.comparison_period.to_dict(),
            "comparison_expenses": None if self.comparison_expenses is None
            else str(self.comparison_expenses),
            "delta": None if self.delta is None else str(self.delta),
            "percentage_change": None if self.percentage_change is None
            else str(self.percentage_change),
        }


def percentage_change(current: Decimal, previous: Decimal | None) -> Decimal | None:
    """Signed percent change of magnitudes; ``None`` when undefined."""
    if previous is None or previous <= 0 or current is None:
        return None
    return ((current - previous) / previous * Decimal("100")).quantize(
        PERCENT_SCALE, rounding=ROUND_HALF_EVEN)


def category_spending_facts(
    db: Session,
    user_id: int,
    observed_period: Period,
    comparison_period: Period | None = None,
    *, exclude_transfers: bool = False,
) -> list[CategorySpendingFact]:
    """Grouped spending facts for a window, optionally versus another.

    Both period totals come from the shared grouped-expenses fact, so every
    consumer (signals, coach recommendations, future dashboards) reads one
    implementation.
    """
    observed_rows = {
        row["category"]: row
        for row in grouped_expenses(
            db, user_id, observed_period.start, observed_period.end,
            limit=ALL_CATEGORIES_LIMIT, exclude_transfers=exclude_transfers)
    }
    comparison_rows: dict[str, dict] = {}
    if comparison_period is not None:
        comparison_rows = {
            row["category"]: row
            for row in grouped_expenses(
                db, user_id, comparison_period.start, comparison_period.end,
                limit=ALL_CATEGORIES_LIMIT, exclude_transfers=exclude_transfers)
        }

    facts: list[CategorySpendingFact] = []
    for category, row in observed_rows.items():
        observed_value = row["expenses"]
        comparison_value = (
            comparison_rows.get(category, {}).get("expenses")
            if comparison_period is not None else None
        )
        facts.append(CategorySpendingFact(
            category=category,
            observed_period=observed_period,
            observed_expenses=observed_value,
            observed_transactions=row["transaction_count"],
            comparison_period=comparison_period,
            comparison_expenses=comparison_value,
            delta=None if comparison_value is None
            else observed_value - comparison_value,
            percentage_change=percentage_change(observed_value, comparison_value),
        ))
    return facts


def comparison_expenses_by_category(
    db: Session,
    user_id: int,
    comparison_period: Period,
) -> dict[str, Decimal]:
    """Observed per-category expenses for one complete comparison month."""
    return {
        row["category"]: row["expenses"]
        for row in grouped_expenses(
            db, user_id, comparison_period.start, comparison_period.end,
            limit=ALL_CATEGORIES_LIMIT)
    }
