from app.services.rag.context import format_retrieved_transactions
from app.services.rag.retrieval import RetrievedTransaction


def test_format_retrieved_transactions():
    transactions = [
        RetrievedTransaction(
            content="Foodpanda - Food - 500.00",
            metadata={
                "transaction_id": 1,
                "user_id": 7,
            },
        ),
        RetrievedTransaction(
            content="Daraz - Shopping - 1500.00",
            metadata={
                "transaction_id": 2,
                "user_id": 7,
            },
        ),
    ]

    context = format_retrieved_transactions(transactions)

    assert "[Transaction 1]" in context
    assert "[Transaction 2]" in context
    assert "Foodpanda" in context
    assert "Daraz" in context


def test_empty_retrieval_context():
    context = format_retrieved_transactions([])

    assert context == "No relevant transactions were found."