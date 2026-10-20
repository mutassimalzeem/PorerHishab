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