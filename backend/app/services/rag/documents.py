from __future__ import annotations

from decimal import Decimal

from app.models.transactions import Transaction


def _format_amount(amount: Decimal) -> str:
    return f"{amount:.2f}"


def transaction_to_document(transaction: Transaction) -> dict:
    """
    Convert one transaction into a retrieval-friendly finance document.

    The document intentionally contains human-readable information rather
    than exposing SQLAlchemy objects to the LLM.
    """

    category = transaction.category or "Uncategorized"
    merchant = transaction.merchant or "Unknown merchant"
    description = transaction.description or ""

    amount = transaction.amount

    if amount > 0:
        transaction_type = "income"
    elif amount < 0:
        transaction_type = "expense"
    else:
        transaction_type = "neutral"

    text = (
        f"Transaction date: {transaction.date}. "
        f"Type: {transaction_type}. "
        f"Amount: {_format_amount(abs(amount))}. "
        f"Merchant: {merchant}. "
        f"Category: {category}. "
        f"Description: {description}. "
    )

    return {
        "page_content": text,
        "metadata": {
            "transaction_id": transaction.id,
            "user_id": transaction.user_id,
            "date": transaction.date.isoformat(),
            "merchant": merchant,
            "category": category,
            "transaction_type": transaction_type,
            "amount": str(amount),
        },
    }


def transactions_to_documents(transactions: list[Transaction]) -> list[dict]:
    
    return [
        transaction_to_document(transaction)
        for transaction in transactions]