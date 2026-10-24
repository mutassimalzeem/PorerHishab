
from typing import Literal

from pydantic import BaseModel, Field


InsightType = Literal[
    "spending_increase",
    "spending_decrease",
    "income_change",
    "savings_rate",
    "top_category",
    "recurring_expense",
    "cashflow_risk",
    "budget_signal",
]

InsightSeverity = Literal["info", "positive", "warning", "critical"]


class FinancialInsight(BaseModel):
    """One concise observation grounded in the user's financial analytics."""

    type: InsightType
    severity: InsightSeverity
    title: str = Field(min_length=3, max_length=100)
    message: str = Field(min_length=10, max_length=500)
    metric: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=100)


class FinancialInsights(BaseModel):
    """Validated collection of AI-generated financial observations."""

    insights: list[FinancialInsight] = Field(default_factory=list, max_length=10)
