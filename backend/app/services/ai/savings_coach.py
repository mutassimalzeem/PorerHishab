
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
    """Optional provider wording; deterministic actions remain available offline."""
    from app.services.ai.provider import build_chat_model

    fallback = [SavingsAction(
        title="Review your contribution plan",
        action="Confirm your reported savings and choose a contribution you can sustain.",
        reason="The plan uses imported history and user-reported savings; future income is uncertain.",
        priority="high" if plan.status == "at_risk" else "medium",
    )]
    if not settings.OPENAI_KEY or not settings.AI_EXTERNAL_ENABLED:
        return fallback
    try:
        model = build_chat_model(settings).with_structured_output(SavingsActionDrafts)
        payload = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False)
        if len(payload) > 12000:
            return fallback
        result = model.invoke([("system", SYSTEM_PROMPT), ("human", payload)])
        drafts = SavingsActionDrafts.model_validate(result.model_dump() if hasattr(result, "model_dump") else result)
        allowed = {item.category for item in plan.recommendations}
        seen = set()
        validated = []
        for action in drafts.actions:
            if action.category is not None:
                if action.category not in allowed or action.category in seen:
                    continue
                seen.add(action.category)
            # Amounts belong exclusively to the deterministic plan.
            if any(character.isdigit() for character in action.action + action.reason + action.title):
                continue
            validated.append(action)
        return validated[:5] or fallback
    except Exception:
        return fallback
