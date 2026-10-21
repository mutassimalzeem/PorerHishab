"""Response schemas for the transaction intelligence API.

Money values are ``Decimal`` end-to-end: the analytics service computes with
``Decimal`` and Pydantic v2 serialises ``Decimal`` in JSON mode without loss
of precision (as a JSON string), so responses stay money-safe.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class SummaryInsight(BaseModel):
    """Income vs expenses, net position, and savings rate."""

    transaction_count: int = Field(..., ge=0)
    total_income: Decimal = Field(..., description="Sum of positive amounts.")
    total_expenses: Decimal = Field(
        ...,
        description="Sum of negative amounts (a negative number).",
    )
    net: Decimal = Field(..., description="total_income + total_expenses.")
    savings_rate: Decimal | None = Field(
        default=None,
        description="net / income, rounded to 4 places. Null when there is no income.",
    )


class MonthlyInsight(BaseModel):
    """One month of the spending breakdown."""

    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM.")
    income: Decimal
    expenses: Decimal = Field(..., description="Negative number.")
    net: Decimal


class GrandTotals(BaseModel):
    """Category-independent totals."""

    income: Decimal
    expenses: Decimal = Field(..., description="Negative number.")
    net: Decimal


class CategoryBreakdown(BaseModel):
    """Spending grouped by category."""

    income_by_category: dict[str, Decimal]
    expenses_by_category: dict[str, Decimal]
    net_by_category: dict[str, Decimal]
    grand_totals: GrandTotals


class MerchantInsight(BaseModel):
    """One entry of the top-merchants ranking."""

    merchant: str
    total_spent: Decimal = Field(
        ...,
        description="Total spent at this merchant (positive magnitude).",
    )
    transaction_count: int = Field(..., ge=1)


class RecurringInsight(BaseModel):
    """A detected recurring charge (subscription, bill, ...)."""

    merchant: str
    occurrences: int = Field(..., ge=1)
    months: int = Field(..., ge=2, description="Distinct months spanned.")
    median_amount: Decimal = Field(..., description="Positive magnitude.")
    total_spent: Decimal = Field(..., description="Positive magnitude.")
    first_date: date
    last_date: date


class CashflowPoint(BaseModel):
    """One day of the cash-flow timeline with a running balance."""

    date: date
    income: Decimal
    expenses: Decimal = Field(..., description="Negative number.")
    net: Decimal
    running_balance: Decimal


class BudgetBaselineCategory(BaseModel):
    """Average monthly spending for one category."""

    category: str
    monthly_average: Decimal = Field(..., description="Positive magnitude.")
    months_observed: int = Field(..., ge=1)


class BudgetBaselineInsight(BaseModel):
    """Suggested budget baseline derived from observed behaviour."""

    months_observed: int = Field(..., ge=0)
    monthly_total_baseline: Decimal = Field(
        ...,
        description="Average total monthly spend (positive magnitude).",
    )
    categories: list[BudgetBaselineCategory]


class InsightsOverview(BaseModel):
    """Every intelligence metric in one payload."""

    summary: SummaryInsight
    monthly: list[MonthlyInsight]
    categories: CategoryBreakdown
    top_merchants: list[MerchantInsight]
    recurring: list[RecurringInsight]
    cashflow: list[CashflowPoint]
    budget_baseline: BudgetBaselineInsight
