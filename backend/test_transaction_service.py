import pandas as pd

from app.services.transaction_service import (
    normalize_transactions,
    categorize_transactions,
)


def test_normalize_transactions():
    df = pd.DataFrame(
        [
            {
                "date": "2026-10-01",
                "description": "Lunch",
                "merchant": "Foodpanda",
                "amount": "-850.50",
                "category": "Food",
            }
        ]
    )

    result = normalize_transactions(df)

    assert len(result) == 1
    assert str(result.iloc[0]["date"]) == "2026-10-01"
    assert float(result.iloc[0]["amount"]) == -850.50


def test_normalize_invalid_amount_is_removed():
    df = pd.DataFrame(
        [
            {
                "date": "2026-10-01",
                "description": "Invalid",
                "merchant": "Test",
                "amount": "not-a-number",
                "category": "Other",
            }
        ]
    )

    result = normalize_transactions(df)

    assert result.empty


def test_existing_category_is_preserved():
    df = pd.DataFrame(
        [
            {
                "date": "2026-10-01",
                "description": "Lunch",
                "merchant": "Foodpanda",
                "amount": -850,
                "category": "Custom Category",
            }
        ]
    )

    result = categorize_transactions(df)

    assert result.iloc[0]["category"] == "Custom Category"


def test_missing_category_uses_new_categorization_pipeline(monkeypatch):
    calls = []

    class Result:
        category = "Food"

    def fake_categorize_transaction(transaction):
        calls.append(transaction)
        return Result()

    monkeypatch.setattr(
        "app.services.transaction_service.categorize_transaction",
        fake_categorize_transaction,
    )

    df = pd.DataFrame(
        [
            {
                "date": "2026-10-01",
                "description": "Food delivery",
                "merchant": "Foodpanda",
                "normalized_merchant": "foodpanda",
                "amount": -850,
                "category": None,
            }
        ]
    )

    result = categorize_transactions(df)

    assert result.iloc[0]["category"] == "Food"
    assert len(calls) == 1
    assert calls[0]["merchant"] == "Foodpanda"
    assert calls[0]["normalized_merchant"] == "foodpanda"


def test_missing_category_falls_back_to_uncategorized(monkeypatch):
    class Result:
        category = "Uncategorized"

    monkeypatch.setattr(
        "app.services.transaction_service.categorize_transaction",
        lambda transaction: Result(),
    )

    df = pd.DataFrame(
        [
            {
                "date": "2026-10-01",
                "description": "Unknown transaction",
                "merchant": "Unknown Merchant",
                "amount": -500,
                "category": None,
            }
        ]
    )

    result = categorize_transactions(df)

    assert result.iloc[0]["category"] == "Uncategorized"