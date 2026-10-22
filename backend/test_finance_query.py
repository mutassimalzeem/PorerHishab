from unittest.mock import Mock, patch

from app.services.finance.query import execute_finance_query
from app.services.finance.router import FinanceIntent


def test_analytics_question_uses_analytics_only():
    db = Mock()

    with (
        patch(
            "app.services.finance.query.get_summary",
            return_value={"net": "25000.00"},
        ),
        patch(
            "app.services.finance.query.get_categories",
            return_value={},
        ),
        patch(
            "app.services.finance.query.get_monthly",
            return_value=[],
        ),
        patch(
            "app.services.finance.query.get_top_merchants",
            return_value=[],
        ),
        patch(
            "app.services.finance.query.get_recurring",
            return_value=[],
        ),
        patch(
            "app.services.finance.query.retrieve_transactions",
        ) as rag_mock,
    ):
        result = execute_finance_query(
            db=db,
            question="How much did I spend?",
            user_id=7,
        )

    assert result.intent == FinanceIntent.ANALYTICS
    assert len(result.evidence) == 5
    rag_mock.assert_not_called()


def test_rag_question_uses_rag_only():
    db = Mock()

    fake_transaction = Mock()
    fake_transaction.content = "Foodpanda - Food - 850"
    fake_transaction.metadata = {
        "transaction_id": 101,
        "user_id": 7,
        "merchant": "Foodpanda",
        "category": "Food",
    }

    with (
        patch(
            "app.services.finance.query.retrieve_transactions",
            return_value=[fake_transaction],
        ),
        patch(
            "app.services.finance.query.get_summary",
        ) as summary_mock,
    ):
        result = execute_finance_query(
            db=db,
            question="Where did I spend money on food?",
            user_id=7,
        )

    assert result.intent == FinanceIntent.RAG
    assert len(result.evidence) == 1
    summary_mock.assert_not_called()


def test_hybrid_question_uses_both():
    db = Mock()

    fake_transaction = Mock()
    fake_transaction.content = "Foodpanda - Food - 850"
    fake_transaction.metadata = {
        "transaction_id": 101,
        "user_id": 7,
        "merchant": "Foodpanda",
        "category": "Food",
    }

    with (
        patch(
            "app.services.finance.query.get_summary",
            return_value={"net": "25000.00"},
        ),
        patch(
            "app.services.finance.query.get_categories",
            return_value={},
        ),
        patch(
            "app.services.finance.query.get_monthly",
            return_value=[],
        ),
        patch(
            "app.services.finance.query.get_top_merchants",
            return_value=[],
        ),
        patch(
            "app.services.finance.query.get_recurring",
            return_value=[],
        ),
        patch(
            "app.services.finance.query.retrieve_transactions",
            return_value=[fake_transaction],
        ),
    ):
        result = execute_finance_query(
            db=db,
            question="Why am I overspending?",
            user_id=7,
        )

    assert result.intent == FinanceIntent.HYBRID
    assert len(result.evidence) == 6


def test_unknown_question_returns_no_evidence():
    db = Mock()

    result = execute_finance_query(
        db=db,
        question="Tell me a joke",
        user_id=7,
    )

    assert result.intent == FinanceIntent.UNKNOWN
    assert result.evidence == []
    assert result.sources == []