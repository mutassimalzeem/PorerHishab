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


def test_categorization_metadata_is_preserved(monkeypatch):
    from app.services import transaction_service
    from app.schemas.categorization import CategorizedTransaction

    monkeypatch.setattr(
        transaction_service,
        "categorize_transaction",
        lambda transaction, **kwargs: CategorizedTransaction(
            category="Food",
            confidence=0.95,
            method="rule",
            reason="Matched Foodpanda merchant rule.",
        ),
    )

    df = pd.DataFrame([
        {
            "date": "2026-10-01",
            "description": "Food delivery",
            "merchant": "Foodpanda",
            "amount": "-850.00",
            "category": None,
        }
    ])

    normalized = normalize_transactions(df)
    result = categorize_transactions(normalized)
    row = result.iloc[0]

    assert row["category"] == "Food"
    assert float(row["category_confidence"]) == 0.95
    assert row["category_method"] == "rule"
    assert row["category_reason"] == "Matched Foodpanda merchant rule."


def test_existing_category_is_not_reclassified():
    df = pd.DataFrame([
        {
            "date": "2026-10-01",
            "description": "Lunch",
            "merchant": "Foodpanda",
            "amount": "-850.00",
            "category": "Custom Category",
        }
    ])

    result = categorize_transactions(normalize_transactions(df))
    row = result.iloc[0]

    assert row["category"] == "Custom Category"
    assert pd.isna(row["category_confidence"])
    assert pd.isna(row["category_method"])
    assert pd.isna(row["category_reason"])
