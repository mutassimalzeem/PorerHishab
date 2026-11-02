from decimal import Decimal

import pytest

from app.schemas.financial_coach import CoachIntent
from app.services.finance.financial_coach_router import (
    route_financial_coach_question,
)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Where does most of my money go?",
            CoachIntent.SPENDING_ANALYSIS,
        ),
        (
            "How much did I spend last month?",
            CoachIntent.SPENDING_ANALYSIS,
        ),
        (
            "Will I run out of money?",
            CoachIntent.CASHFLOW,
        ),
        (
            "Can I afford a laptop for ৳80,000?",
            CoachIntent.AFFORDABILITY,
        ),
        (
            "How can I save more?",
            CoachIntent.SAVINGS,
        ),
        (
            "Help me save for a laptop.",
            CoachIntent.GOAL_PLANNING,
        ),
        (
            "Which scenario is safer?",
            CoachIntent.SCENARIO_COMPARISON,
        ),
        (
            "Why did I receive this alert?",
            CoachIntent.ALERT_EXPLANATION,
        ),
        (
            "How healthy are my finances?",
            CoachIntent.FINANCIAL_HEALTH,
        ),
        (
            "What is an emergency fund?",
            CoachIntent.GENERAL_FINANCE,
        ),
    ],
)
def test_routes_supported_intents(question, expected):
    result = route_financial_coach_question(question)

    assert result.intent == expected
    assert result.confidence > 0
    assert result.requires_clarification is False


def test_extracts_explicit_bdt_amount():
    result = route_financial_coach_question(
        "Can I afford a laptop for ৳80,000?"
    )

    assert result.intent == CoachIntent.AFFORDABILITY
    assert result.extracted_amount == Decimal("80000")


def test_extracts_taka_amount():
    result = route_financial_coach_question(
        "Can I purchase this for 25,000 taka?"
    )

    assert result.extracted_amount == Decimal("25000")


def test_does_not_infer_amount_without_currency():
    result = route_financial_coach_question(
        "Can I afford a laptop for 80000?"
    )

    assert result.intent == CoachIntent.AFFORDABILITY
    assert result.extracted_amount is None


def test_does_not_extract_multiple_amounts():
    result = route_financial_coach_question(
        "Can I afford something costing ৳80,000 or ৳90,000?"
    )

    assert result.extracted_amount is None


def test_unknown_question_requires_clarification():
    result = route_financial_coach_question(
        "Tell me something interesting."
    )

    assert result.intent == CoachIntent.UNKNOWN
    assert result.requires_clarification is True


def test_empty_question_is_rejected():
    with pytest.raises(ValueError):
        route_financial_coach_question("   ")


def test_conflicting_intents_require_clarification():
    result = route_financial_coach_question(
        "Can I afford this purchase and how can I save more?"
    )

    assert result.intent == CoachIntent.UNKNOWN
    assert result.requires_clarification is True
