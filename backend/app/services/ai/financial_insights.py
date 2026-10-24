
"""Generate grounded financial insights from deterministic analytics."""

from __future__ import annotations

import json
import os
from typing import Any
from dotenv import load_dotenv


from app.schemas.financial_insights import FinancialInsights


SYSTEM_PROMPT = """
You are Zyra, a careful personal finance coach.

You will receive structured financial analytics already calculated by Python.

Rules:
- Treat the supplied analytics as the only source of financial facts.
- Never invent transactions, amounts, percentages, merchants, or categories.
- Never recalculate or alter supplied financial figures.
- Do not interpret missing data as zero.
- Do not claim a trend unless the supplied data supports it.
- Expenses in the monthly breakdown may be negative; expense changes in the
  month_over_month data are expressed as positive spending magnitudes.
- A positive expense_change means spending increased; a negative value means
  spending decreased.
- If a percentage is null, do not invent a percentage.
- Return at most 6 useful, non-duplicative insights.
- Prefer meaningful changes, unusually high spending, savings-rate signals,
  recurring expenses, and negative net cash flow.
- Be concise, supportive, specific, and practical.
- Do not provide investment, tax, legal, or lending advice.
- Do not shame the user for their spending.
- If the data is insufficient, return fewer insights or an empty list.
"""


def _prepare_analytics(analytics: dict[str, Any]) -> str:
    """Serialize calculated analytics without losing Decimal/date values."""
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
    """Ask the configured OpenAI model to explain existing financial signals.

    Requires OPENAI_API_KEY. Financial calculations remain outside the LLM.
    """
    
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Add it to your local .env file."
        )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "langchain-openai is not installed. Install it in the project "
            "virtual environment before using AI financial insights."
        ) from exc

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        temperature=0,
        timeout=30,
        max_retries=2,
    )

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

    # Defensive validation in case a provider returns a dictionary.
    return FinancialInsights.model_validate(result)
