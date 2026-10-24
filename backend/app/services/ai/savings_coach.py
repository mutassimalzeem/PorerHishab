
"""Generate practical savings actions grounded in the deterministic plan."""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.schemas.planner import SavingsPlanResponse
from app.schemas.savings_coach import SavingsAction, SavingsActionDrafts


SYSTEM_PROMPT = """
You are PorerHishab, a supportive personal finance coach.

You will receive a savings plan calculated by the application.

Rules:
- Use only the supplied plan as your financial evidence.
- Never invent or change amounts, dates, percentages, or category spending.
- Suggest realistic, specific actions rather than generic motivational advice.
- If the goal is complete or already on track, do not invent a spending problem.
- If the plan is at risk, prioritize the supplied spending-cut categories.
- Do not shame the user or recommend cutting essential needs.
- Do not give investment, tax, legal, or lending advice.
- Return at most 5 concise actions.
- The application will attach authoritative monthly amounts to matching
  categories; do not include financial figures in your action text.
"""


def generate_savings_actions(plan: SavingsPlanResponse) -> list[SavingsAction]:
    """Use an LLM to explain a savings plan without changing its calculations."""
    
    if not settings.OPENAI_KEY:
        raise RuntimeError(
            "OPENAI_KEY is not configured. Add it to your root .env file.")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "langchain-openai is not installed. Install the dependency "
            "in the project virtual environment."
        ) from exc

    options: dict[str, Any] = {
        "model": settings.OPENAI_CHAT_MODEL,
        "api_key": settings.OPENAI_KEY,
        "temperature": 0,
        "timeout": 30,
        "max_retries": 2,
    }
    if settings.OPENAI_BASE_URL:
        options["base_url"] = settings.OPENAI_BASE_URL

    model = ChatOpenAI(**options).with_structured_output(SavingsActionDrafts)

    plan_data = plan.model_dump(mode="json")
    result = model.invoke(
        [
            ("system", SYSTEM_PROMPT),
            (
                "human",
                "Create personalized savings actions for this plan:\n"
                + json.dumps(plan_data, ensure_ascii=False),
            ),
        ]
    )

    drafts = (
        result
        if isinstance(result, SavingsActionDrafts)
        else SavingsActionDrafts.model_validate(result)
    )

    # Only allow categories supported by the deterministic planner.
    allowed_categories = {
        item.category
        for item in plan.recommendations
    }

    validated: list[SavingsAction] = []
    seen_categories: set[str] = set()

    for action in drafts.actions:
        if action.category is not None:
            if action.category not in allowed_categories:
                continue
            if action.category in seen_categories:
                continue
            seen_categories.add(action.category)

        validated.append(action)

        if len(validated) == 5:
            break

    return validated
