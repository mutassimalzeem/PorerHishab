from datetime import date
from decimal import Decimal

from app.models.transactions import Transaction
from app.services.rag.documents import transaction_to_document
from app.services.rag.vector_store import transaction_dict_to_document


def test_transaction_dict_to_document():
    transaction = Transaction(
        id=101,
        user_id=7,
        date=date(2026, 10, 21),
        merchant="Foodpanda",
        description="Dinner",
        category="Food",
        amount=Decimal("-850.00"),
    )

    transaction_dict = transaction_to_document(transaction)

    document = transaction_dict_to_document(transaction_dict)

    assert document.page_content
    assert "Foodpanda" in document.page_content
    assert document.metadata["transaction_id"] == 101
    assert document.metadata["user_id"] == 7
    assert document.metadata["category"] == "Food"


def test_document_has_user_metadata():
    transaction = Transaction(
        id=102,
        user_id=42,
        date=date(2026, 10, 21),
        merchant="Daraz",
        description="Online purchase",
        category="Shopping",
        amount=Decimal("-1200.00"))

    transaction_dict = transaction_to_document(transaction)
    document = transaction_dict_to_document(transaction_dict)

    assert document.metadata["user_id"] == 42