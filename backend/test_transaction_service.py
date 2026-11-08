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


def test_csv_import_many_uncategorized_caps_llm_provider_calls(monkeypatch):
    """A CSV with many uncategorized rows must not exceed the 5-call LLM budget."""
    import io
    from unittest.mock import MagicMock
    from app.core.config import settings
    from app.services.categorization.budget import DEFAULT_CATEGORIZATION_BUDGET
    import app.services.categorization.llm as llm_module
    from app.services import transaction_service

    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", True)

    provider_call_count = 0

    class MockChatModel:
        def invoke(self, messages):
            nonlocal provider_call_count
            provider_call_count += 1
            mock_response = MagicMock()
            mock_response.content = '{"category": "Other", "confidence": 0.8, "reason": "Mocked LLM"}'
            return mock_response

    monkeypatch.setattr(llm_module, "get_chat_model", lambda: MockChatModel())

    # CSV containing 12 uncategorized transactions (exceeds budget of 5)
    csv_text = "date,amount,merchant,description\n" + "\n".join(
        f"2026-10-01,-100.00,Mysterious Merchant {i},Unrecognized Item {i}"
        for i in range(12)
    )
    df = pd.read_csv(io.StringIO(csv_text))
    normalized = normalize_transactions(df)

    result = categorize_transactions(normalized)

    # Assert that no more than five provider calls occur for that import
    assert provider_call_count == DEFAULT_CATEGORIZATION_BUDGET
    assert provider_call_count <= 5

    # First 5 were categorized by LLM
    llm_rows = result[result["category_method"] == "llm"]
    assert len(llm_rows) == 5

    # Remaining 7 degraded to fallback Uncategorized
    fallback_rows = result[result["category_method"] == "fallback"]
    assert len(fallback_rows) == 7
    for _, row in fallback_rows.iterrows():
        assert row["category"] == "Uncategorized"
        assert "limit reached" in row["category_reason"]


def test_csv_save_transactions_caps_llm_provider_calls(monkeypatch):
    """End-to-end import via save_transactions adheres to the 5-call budget."""
    import io
    from unittest.mock import MagicMock
    from app.core.config import settings
    from app.services.categorization.budget import DEFAULT_CATEGORIZATION_BUDGET
    import app.services.categorization.llm as llm_module
    from app.services import transaction_service

    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", True)

    provider_call_count = 0

    class MockChatModel:
        def invoke(self, messages):
            nonlocal provider_call_count
            provider_call_count += 1
            mock_response = MagicMock()
            mock_response.content = '{"category": "Other", "confidence": 0.8, "reason": "Mocked LLM"}'
            return mock_response

    monkeypatch.setattr(llm_module, "get_chat_model", lambda: MockChatModel())

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(transaction_service, "SessionLocal", lambda: mock_db)
    monkeypatch.setattr(transaction_service, "create_transactions", lambda db, txs: txs)

    csv_text = "date,amount,merchant,description\n" + "\n".join(
        f"2026-10-01,-100.00,Vendor {i},Item {i}"
        for i in range(10)
    )
    df = pd.read_csv(io.StringIO(csv_text))

    import_result = transaction_service.save_transactions(df, user_id=1, detailed=True)

    assert provider_call_count == DEFAULT_CATEGORIZATION_BUDGET
    assert provider_call_count <= 5
    assert import_result.rows_persisted == 10
    llm_saved = [t for t in import_result.transactions if t.category_method == "llm"]
    assert len(llm_saved) == 5
    fallback_saved = [t for t in import_result.transactions if t.category_method == "fallback"]
    assert len(fallback_saved) == 5


def test_csv_import_llm_provider_exception_still_consumes_budget(monkeypatch):
    """Exceptions at provider-call boundary still consume budget slots consistently."""
    import io
    from app.core.config import settings
    from app.services.categorization.budget import DEFAULT_CATEGORIZATION_BUDGET
    import app.services.categorization.llm as llm_module
    from app.services.transaction_service import (
        normalize_transactions,
        categorize_transactions,
    )

    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", True)

    provider_call_count = 0

    class FailingChatModel:
        def invoke(self, messages):
            nonlocal provider_call_count
            provider_call_count += 1
            raise RuntimeError("Provider network timeout")

    monkeypatch.setattr(llm_module, "get_chat_model", lambda: FailingChatModel())

    csv_text = "date,amount,merchant,description\n" + "\n".join(
        f"2026-10-01,-100.00,Vendor {i},Item {i}"
        for i in range(10)
    )
    df = pd.read_csv(io.StringIO(csv_text))
    normalized = normalize_transactions(df)

    result = categorize_transactions(normalized)

    # Provider was called 5 times, then stopped because budget exhausted
    assert provider_call_count == DEFAULT_CATEGORIZATION_BUDGET
    assert provider_call_count <= 5
    assert len(result[result["category_method"] == "fallback"]) == 10
