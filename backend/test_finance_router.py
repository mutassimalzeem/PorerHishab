from app.services.finance.router import (FinanceIntent, route_finance_question)


def test_exact_amount_question_routes_to_analytics():
    assert (
        route_finance_question("How much did I spend on food?")
        == FinanceIntent.ANALYTICS
    )


def test_monthly_question_routes_to_analytics():
    assert (
        route_finance_question(
            "How much did I spend in September?"
        )
        == FinanceIntent.ANALYTICS
    )


def test_comparison_question_routes_to_analytics():
    assert (
        route_finance_question(
            "Compare September and October spending"
        )
        == FinanceIntent.ANALYTICS
    )


def test_advice_question_routes_to_hybrid():
    assert (
        route_finance_question(
            "What should I cut to save more?"
        )
        == FinanceIntent.HYBRID
    )


def test_overspending_question_routes_to_hybrid():
    assert (
        route_finance_question(
            "Why am I overspending?"
        )
        == FinanceIntent.HYBRID
    )


def test_transaction_question_routes_to_rag():
    assert (
        route_finance_question(
            "Where did I spend money on food?"
        )
        == FinanceIntent.RAG
    )


def test_empty_question_rejected():
    import pytest

    with pytest.raises(ValueError):
        route_finance_question("   ")


def test_unknown_question():
    assert (
        route_finance_question(
            "Tell me a joke"
        )
        == FinanceIntent.UNKNOWN
    )