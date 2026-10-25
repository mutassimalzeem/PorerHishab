
"""Generate grounded financial insights from deterministic analytics."""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.schemas.financial_insights import FinancialInsights


SYSTEM_PROMPT = """
You are PorerHishab, a careful personal finance coach.

You will receive structured financial analytics calculated by Python.

Rules:
- Use the supplied analytics as your only source of financial facts.
- Never invent or alter financial figures, percentages, merchants, or categories.
- Do not interpret missing data as zero.
- Do not claim trends that the supplied data does not support.
- Expenses are negative in monthly and category breakdowns.
- Expense changes in month_over_month are calculated by the application.
- If a percentage is null, do not invent one.
- Return at most 6 useful, non-duplicative insights.
- Prioritize meaningful spending changes, savings-rate signals, recurring
  expenses, budget signals, and negative net cash flow.
- Be concise, supportive, specific, and practical.
- Do not shame the user for spending.
- Do not provide investment, tax, legal, or lending advice.
- If data is insufficient, return fewer insights or an empty list.
"""


def _prepare_analytics(analytics: dict[str, Any]) -> str:
    """Serialize approved aggregate analytics, excluding raw transactions."""
    allowed_keys = (
        "summary",
        "monthly",
        "month_over_month",
        "categories",
        "top_merchants",
        "recurring",
        "budget_baseline",
    )

    payload = {
        key: analytics[key]
        for key in allowed_keys
        if key in analytics
    }

    return json.dumps(payload, default=str, ensure_ascii=False)


def generate_financial_insights(analytics: dict[str, Any]) -> FinancialInsights:
    """Provider can select grounded observations, never author financial claims."""
    from decimal import Decimal, InvalidOperation
    from typing import Annotated
    from pydantic import BaseModel, ConfigDict, Field
    from app.schemas.financial_insights import FinancialInsight
    from app.services.ai.provider import structured_optional

    class Selection(BaseModel):
        model_config = ConfigDict(extra="forbid")
        indices: list[Annotated[int, Field(ge=0, le=5)]] = Field(max_length=6)

    monthly = analytics.get("monthly") or []
    candidates = []
    if not monthly:
        return FinancialInsights()
    last = monthly[-1]
    try:
        net = Decimal(str(last.get("net")))
        if net.is_finite() and net < 0:
            candidates.append(FinancialInsight(type="cashflow_risk", severity="warning",
                title="Recorded expenses exceed income",
                message="Review the latest recorded month's spending and confirm import completeness before changing your plan."))
        elif net.is_finite() and net > 0:
            candidates.append(FinancialInsight(type="savings_rate", severity="positive",
                title="Recorded income exceeds expenses",
                message="The latest recorded month has a positive net amount; confirm missing bills before committing it to savings."))
    except (InvalidOperation, TypeError, ValueError):
        pass
    if not candidates:
        return FinancialInsights()
    payload = json.dumps([item.model_dump() for item in candidates], ensure_ascii=False)
    selection = structured_optional(Selection,
        "Select useful supplied observation indices only. Do not create observations or financial claims. Return JSON with indices.", payload)
    if selection is not None:
        chosen = [candidates[index] for index in dict.fromkeys(selection.indices) if index < len(candidates)]
        if chosen:
            return FinancialInsights(insights=chosen)
    return FinancialInsights(insights=candidates)
