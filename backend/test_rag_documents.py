from datetime import date
from decimal import Decimal
from app.models.transactions import Transaction
from app.services.rag.documents import transaction_to_document, transactions_to_documents

def test_transaction_to_document():
    transaction = Transaction(id = 1, user_id = 7, date = date(2026, 10, 21), merchant = "Foodpanda",
                              description = "Dinner order", category = "Food",
                              amount = Decimal("-850.00"))

    document = transaction_to_document(transaction)

    assert "Foodpanda" in document["page_content"]
    assert "850.00" in document["page_content"]
    assert "Food" in document["page_content"]
    assert "Dinner order" in document["page_content"]

    assert document["metadata"]["transaction_id"] == 1
    assert document["metadata"]["user_id"] == 7
    assert document["metadata"]["merchant"] == "Foodpanda"
    assert document["metadata"]["category"] == "Food"
    assert document["metadata"]["transaction_type"] == "expense"


def test_income_transaction():

    transaction = Transaction(
        id=102,
        user_id=7,
        date=date(2026, 10, 21),
        merchant="Salary",
        description="Monthly salary",
        category="Income",
        amount=Decimal("50000.00"),
    )

    document = transaction_to_document(transaction)

    assert document["metadata"]["transaction_type"] == "income"
    assert "50000.00" in document["page_content"]


def test_transactions_to_documents():

    transactions = [
        Transaction(
            id=1,
            user_id=7,
            date=date(2026, 10, 1),
            merchant="Foodpanda",
            category="Food",
            amount=Decimal("-500.00"),
        ),
        Transaction(
            id=2,
            user_id=7,
            date=date(2026, 10, 2),
            merchant="Salary",
            category="Income",
            amount=Decimal("50000.00"),
        ),
    ]

    documents = transactions_to_documents(transactions)

    assert len(documents) == 2
    assert documents[0]["metadata"]["transaction_id"] == 1
    assert documents[1]["metadata"]["transaction_id"] == 2