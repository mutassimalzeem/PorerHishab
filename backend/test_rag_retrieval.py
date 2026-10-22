from unittest.mock import patch

import pytest

from app.services.rag.retrieval import retrieve_transactions


def test_retrieve_transactions():
    fake_documents = [
        type(
            "FakeDocument",
            (),
            {
                "page_content": (
                    "Transaction date: 2026-10-01. "
                    "Type: expense. "
                    "Amount: 500.00. "
                    "Merchant: Foodpanda. "
                    "Category: Food."
                ),
                "metadata": {
                    "transaction_id": 1,
                    "user_id": 7,
                    "category": "Food",
                },
            },
        )()
    ]

    with patch(
        "app.services.rag.retrieval.search_transactions",
        return_value=fake_documents,
    ) as mock_search:
        results = retrieve_transactions(
            query="Where did I spend money on food?",
            user_id=7,
            k=5,
        )

    mock_search.assert_called_once_with(
        query="Where did I spend money on food?",
        user_id=7,
        k=5,
    )

    assert len(results) == 1
    assert results[0].metadata["transaction_id"] == 1
    assert results[0].metadata["user_id"] == 7
    assert "Foodpanda" in results[0].content


def test_empty_query_rejected():
    with pytest.raises(ValueError):
        retrieve_transactions(
            query="   ",
            user_id=7,
        )


def test_invalid_user_id_rejected():
    with pytest.raises(ValueError):
        retrieve_transactions(
            query="food",
            user_id=0,
        )


def test_invalid_k_rejected():
    with pytest.raises(ValueError):
        retrieve_transactions(
            query="food",
            user_id=7,
            k=0,
        )