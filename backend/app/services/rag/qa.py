from __future__ import annotations

from dataclasses import dataclass

from app.services.rag.chat_model import get_chat_model
from app.services.rag.context import format_retrieved_transactions
from app.services.rag.prompts import FINANCE_QA_PROMPT
from app.services.rag.retrieval import retrieve_transactions


@dataclass
class FinanceAnswer:
    answer: str
    sources: list[dict]


def answer_finance_question(
    question: str,
    user_id: int,
    k: int = 5) -> FinanceAnswer:

    question = question.strip()

    if not question:
        raise ValueError("Question cannot be empty.")

    transactions = retrieve_transactions(
        query=question,
        user_id=user_id,
        k=k,
    )

    transactions = [item for item in transactions if item.metadata.get("user_id") == user_id]

    context = format_retrieved_transactions(transactions)

    prompt = FINANCE_QA_PROMPT.invoke(
        {
            "context": context,
            "question": question,
        }
    )

    model = get_chat_model()

    response = model.invoke(prompt)

    sources = [
        {
            "transaction_id": transaction.metadata.get(
                "transaction_id"
            ),
            "date": transaction.metadata.get("date"),
            "merchant": transaction.metadata.get("merchant"),
            "category": transaction.metadata.get("category"),
            "amount": transaction.metadata.get("amount"),
        }
        for transaction in transactions
    ]

    return FinanceAnswer(answer=response.content, sources=sources)