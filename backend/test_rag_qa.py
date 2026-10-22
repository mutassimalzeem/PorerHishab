from unittest.mock import patch

from app.services.rag.qa import answer_finance_question
from app.services.rag.retrieval import RetrievedTransaction


class FakeResponse:
    content = "You spent 850.00 on Foodpanda for food."


def test_answer_finance_question():
    transactions = [
        RetrievedTransaction(
            content=(
                "Transaction date: 2026-10-21. "
                "Type: expense. "
                "Amount: 850.00. "
                "Merchant: Foodpanda. "
                "Category: Food. "
                "Description: Dinner."
            ),
            metadata={
                "transaction_id": 101,
                "user_id": 7,
                "date": "2026-10-21",
                "merchant": "Foodpanda",
                "category": "Food",
                "transaction_type": "expense",
                "amount": "-850.00",
            },
        )
    ]

    fake_model = type(
        "FakeModel",
        (),
        {
            "invoke": lambda self, prompt: FakeResponse(),
        },
    )()

    with patch(
        "app.services.rag.qa.retrieve_transactions",
        return_value=transactions,
    ), patch(
        "app.services.rag.qa.get_chat_model",
        return_value=fake_model,
    ):
        result = answer_finance_question(
            question="How much did I spend on Foodpanda?",
            user_id=7,
        )

    assert "850.00" in result.answer
    assert len(result.sources) == 1
    assert result.sources[0]["transaction_id"] == 101


def test_empty_question_rejected():
    from pytest import raises

    with raises(ValueError):
        answer_finance_question(
            question="   ",
            user_id=7,
        )



from app.services.rag.prompts import FINANCE_QA_PROMPT


def test_finance_prompt_contains_guardrails():
    messages = FINANCE_QA_PROMPT.invoke(
        {
            "context": "Foodpanda - 500",
            "question": "How much did I spend?",
        }
    )

    prompt_text = str(messages)

    assert "Never invent" in prompt_text
    assert "provided context" in prompt_text
    assert "database details" in prompt_text