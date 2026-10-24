
"""Generate grounded financial insights from deterministic analytics."""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.schemas.financial_insights import FinancialInsights


SYSTEM_PROMPT = """
You are Zyra, a careful personal finance coach.

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


def generate_financial_insights(
    analytics: dict[str, Any],
) -> FinancialInsights:
    """Explain application-calculated analytics using the configured LLM."""
    if not settings.OPENAI_KEY:
        raise RuntimeError(
            "OPENAI_KEY is not configured. Add it to your root .env file."
        )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "langchain-openai is not installed. Install the dependency "
            "in the project virtual environment."
        ) from exc

    llm_options: dict[str, Any] = {
        "model": settings.OPENAI_CHAT_MODEL,
        "api_key": settings.OPENAI_KEY,
        "temperature": 0,
        "timeout": 30,
        "max_retries": 2,
    }

    if settings.OPENAI_BASE_URL:
        llm_options["base_url"] = settings.OPENAI_BASE_URL

    llm = ChatOpenAI(**llm_options)
    structured_llm = llm.with_structured_output(FinancialInsights)

    result = structured_llm.invoke(
        [
            ("system", SYSTEM_PROMPT),
            (
                "human",
                "Generate useful financial observations from these "
                "application-calculated analytics:\n\n"
                + _prepare_analytics(analytics),
            ),
        ]
    )

    if isinstance(result, FinancialInsights):
        return result
    
    return FinancialInsights.model_validate(result)
