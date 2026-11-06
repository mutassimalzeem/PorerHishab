
"""Deterministic intent routing for the financial coach.

This module classifies a user's question. It does not query financial
records, perform calculations, or invoke an LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.schemas.financial_coach import CoachIntent


@dataclass(frozen=True)
class IntentRoute:
    """The result of routing a financial question."""

    intent: CoachIntent
    confidence: Decimal
    matched_signals: tuple[str, ...]
    requires_clarification: bool = False
    extracted_amount: Decimal | None = None


# Order matters: more specific financial questions are checked first.
INTENT_PATTERNS: tuple[tuple[CoachIntent, tuple[str, ...]], ...] = (
    (
        CoachIntent.FINANCIAL_REVIEW,
        (
            "financial review",
            "আর্থিক পর্যালোচনা",
            "আমার অগ্রাধিকার ব্যাখ্যা",
            "explain my financial review",
            "explain my review",
            "review my financial plan",
            "review my priorities",
            "explain my priorities",
            "why are these priorities",
            "why are my priorities",
            "what should i review first",
            "what should i do first",
            "which priority comes first",
            "financial plan review",
            "plan review",
            "explain my plan",
            "why is this step blocked",
            "why are these steps blocked",
            "what is blocking my plan",
            "what is blocking",
        ),
    ),
    (
        CoachIntent.SCENARIO_COMPARISON,
        (
            "compare these scenarios",
            "compare the scenarios",
            "which scenario",
            "which option is safer",
            "what if",
            "scenario comparison",
        ),
    ),
    (
        CoachIntent.AFFORDABILITY,
        (
            "can i afford",
            "could i afford",
            "should i buy",
            "should i purchase",
            "is it affordable",
            "can i buy",
            "can i purchase",
        ),
    ),
    (
        CoachIntent.GOAL_PLANNING,
        (
            "saving goal",
            "savings goal",
            "save for",
            "help me save",
            "plan to save",
            "reach my goal",
            "goal deadline",
            "goal planning",
        ),
    ),
    (
        CoachIntent.ALERT_EXPLANATION,
        (
            "why did i receive this alert",
            "explain this alert",
            "why am i getting this alert",
            "what does this alert mean",
            "explain my notification",
        ),
    ),
    (
        CoachIntent.FINANCIAL_HEALTH,
        (
            "financial health",
            "financially healthy",
            "how healthy are my finances",
            "health of my finances",
            "financial health score",
        ),
    ),
    (
        CoachIntent.CASHFLOW,
        (
            "cash flow",
            "cashflow",
            "run out of money",
            "money run out",
            "future balance",
            "projected balance",
            "cash position",
            "financial runway",
            "forecast my balance",
        ),
    ),
    (
        CoachIntent.SAVINGS,
        (
            "how can i save",
            "how do i save",
            "save more",
            "saving opportunities",
            "savings opportunities",
            "reduce my expenses",
            "cut my spending",
            "where can i save",
        ),
    ),
    (
        CoachIntent.SPENDING_ANALYSIS,
        (
            "where does my money go",
            "where does most of my money go",
            "where does all my money go",
            "where did my money go",
            "where is my money going",
            "how much did i spend",
            "how much have i spent",
            "my spending",
            "my expenses",
            "spending breakdown",
            "expense breakdown",
            "highest spending",
            "top spending categories",
            "overspending",
        ),
    ),
    (
        CoachIntent.GENERAL_FINANCE,
        (
            "what is a budget",
            "explain budgeting",
            "what is an emergency fund",
            "what is compound interest",
            "financial advice",
            "money management",
        ),
    ),
)


AMOUNT_PATTERN = re.compile(
    r"(?:৳|bdt\s*)\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)"
    r"|([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)\s*(?:bdt|taka|tk)\b",
    re.IGNORECASE,
)


def _extract_amount(question: str) -> Decimal | None:
    """Extract one explicit BDT amount; never infer an amount."""

    matches = list(AMOUNT_PATTERN.finditer(question))

    # Multiple amounts need more sophisticated interpretation.
    if len(matches) != 1:
        return None

    raw_amount = matches[0].group(1) or matches[0].group(2)

    try:
        amount = Decimal(raw_amount.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None

    if not amount.is_finite() or amount <= 0:
        return None

    return amount


def route_financial_coach_question(question: str) -> IntentRoute:
    """Classify a financial question using deterministic phrase matching.

    The router deliberately returns UNKNOWN when no supported intent
    is detected. It does not guess based on a weak keyword match.
    """

    normalized = " ".join(question.strip().lower().split())

    if not normalized:
        raise ValueError("Question cannot be empty.")

    matched_intents: list[tuple[CoachIntent, tuple[str, ...]]] = []

    for intent, patterns in INTENT_PATTERNS:
        matched = tuple(
            pattern
            for pattern in patterns
            if pattern in normalized
        )

        if matched:
            matched_intents.append((intent, matched))

    if not matched_intents:
        return IntentRoute(
            intent=CoachIntent.UNKNOWN,
            confidence=Decimal("0"),
            matched_signals=(),
            requires_clarification=True,
        )

    # If distinct intent families match, do not silently choose one.
    distinct_intents = {item[0] for item in matched_intents}

    if len(distinct_intents) > 1:
        return IntentRoute(
            intent=CoachIntent.UNKNOWN,
            confidence=Decimal("0.25"),
            matched_signals=tuple(
                signal
                for _, signals in matched_intents
                for signal in signals
            ),
            requires_clarification=True,
            extracted_amount=_extract_amount(normalized),
        )

    intent, signals = matched_intents[0]

    return IntentRoute(
        intent=intent,
        confidence=Decimal("0.90"),
        matched_signals=signals,
        requires_clarification=False,
        extracted_amount=_extract_amount(normalized),
    )
