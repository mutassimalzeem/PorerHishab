from unittest.mock import Mock, patch

from app.services.finance.service import answer_finance_query
from app.services.finance.router import FinanceIntent


def test_finance_service_generates_grounded_answer():
    db = Mock()

    fake_result = Mock()
    fake_result.intent = FinanceIntent.ANALYTICS
    fake_result.sources = []
    fake_result.evidence = [
        Mock(
            source_type="analytics",
            data={"net": "25000.00"},
            description="Summary",
        )
    ]

    with (
        patch(
            "app.services.finance.service.execute_finance_query",
            return_value=fake_result,
        ),
        patch(
            "app.services.finance.service.generate_finance_answer",
            return_value="Your net position is 25,000.00.",
        ) as answer_mock,
    ):
        result = answer_finance_query(
            db=db,
            question="How much money do I have left?",
            user_id=7,
        )

    assert result.intent == FinanceIntent.ANALYTICS
    assert "25,000.00" in result.answer
    answer_mock.assert_called_once()


def test_unknown_question_does_not_call_llm():
    db = Mock()

    fake_result = Mock()
    fake_result.intent = FinanceIntent.UNKNOWN
    fake_result.sources = []
    fake_result.evidence = []

    with (
        patch(
            "app.services.finance.service.execute_finance_query",
            return_value=fake_result,
        ),
        patch(
            "app.services.finance.service.generate_finance_answer",
        ) as answer_mock,
    ):
        result = answer_finance_query(
            db=db,
            question="Tell me a joke",
            user_id=7,
        )

    assert result.intent == FinanceIntent.UNKNOWN
    assert result.sources == []
    answer_mock.assert_not_called()