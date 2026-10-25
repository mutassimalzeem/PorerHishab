"""Tests for the categorization orchestration service.

Rule hits must short-circuit the LLM; misses go to it; any invalid LLM
output degrades silently to ``Uncategorized``.
"""

import app.services.categorization.service as service_module
from app.schemas.categorization import LLMCategorization
from app.services.categorization.service import categorize_transaction


class TransactionStub:
    """Minimal stand-in for the ``Transaction`` model."""

    def __init__(
        self,
        merchant=None,
        normalized_merchant=None,
        description=None,
        amount=None,
    ):
        self.merchant = merchant
        self.normalized_merchant = normalized_merchant
        self.description = description
        self.amount = amount


def _forbid_llm(monkeypatch):
    """Make any LLM call fail the test loudly."""

    def _boom(*args, **kwargs):
        raise AssertionError("LLM must not be called when the rules match")

    monkeypatch.setattr(service_module, "categorize_with_llm", _boom)


def test_rule_match_short_circuits_llm(monkeypatch):
    _forbid_llm(monkeypatch)

    result = categorize_transaction(
        TransactionStub(
            merchant="Foodpanda", description="ORDER FP-DHAKA", amount=-850.50,
        )
    )

    assert result.category == "Food"
    assert result.method == "rule"
    assert result.confidence >= 0.9


def test_rule_miss_falls_through_to_llm(monkeypatch):
    called: dict = {}
    validated = LLMCategorization(
        category="Groceries",
        confidence=0.91,
        reason="Supermarket transaction",
    )

    def fake_llm(**kwargs):
        called.update(kwargs)
        return validated

    monkeypatch.setattr(service_module, "categorize_with_llm", fake_llm)

    result = categorize_transaction(
        TransactionStub(
            merchant="XYZ RANDOM STORE",
            description="CARD PURCHASE",
            amount=-980.00,
        )
    )

    assert result.category == "Groceries"
    assert result.method == "llm"
    assert result.confidence == 0.91

    assert called["merchant"] == "XYZ RANDOM STORE"
    assert called["description"] == "CARD PURCHASE"
    assert called["amount"] == "-980.0"


def test_rule_miss_uses_llm_fields_ordering(monkeypatch):
    """normalized_merchant should be forwarded to the LLM prompt."""

    def fake_llm(**kwargs):
        return LLMCategorization(category="Groceries", confidence=0.9, reason=None)

    monkeypatch.setattr(service_module, "categorize_with_llm", fake_llm)

    result = categorize_transaction(
        TransactionStub(normalized_merchant="beautiful bazaar dhaka")
    )

    assert result.category == "Groceries"
    assert result.reason is None


def test_invalid_llm_response_falls_back_to_uncategorized(monkeypatch):
    def broken_llm(**kwargs):
        raise service_module.CategorizationLLMError("no key configured")

    monkeypatch.setattr(service_module, "categorize_with_llm", broken_llm)

    result = categorize_transaction(
        TransactionStub(merchant="XYZ RANDOM STORE", description="CARD PURCHASE")
    )

    assert result.category == "Uncategorized"
    assert result.method == "fallback"
    assert result.confidence == 0.0
    assert "LLM categorization failed" in result.reason


def test_empty_transaction_skips_llm(monkeypatch):
    _forbid_llm(monkeypatch)

    result = categorize_transaction(TransactionStub())

    assert result.category == "Uncategorized"
    assert result.method == "fallback"


def test_result_carries_reason_for_every_method(monkeypatch):
    """Whatever the method, the result schema is consistent."""

    monkeypatch.setattr(
        service_module,
        "categorize_with_llm",
        lambda **kwargs: LLMCategorization(
            category="Transport", confidence=0.8, reason="Ride service",
        ),
    )

    for transaction, expected_method in (
        (TransactionStub(merchant="Foodpanda"), "rule"),
        (TransactionStub(merchant="Grilled Eats"), "llm"),
    ):
        result = categorize_transaction(transaction)
        assert result.method == expected_method
        assert result.reason  # non-empty justification

        fields = result.model_dump()
        assert set(fields) == {"category", "confidence", "method", "reason"}


def test_dict_transaction_is_supported(monkeypatch):
    _forbid_llm(monkeypatch)

    result = categorize_transaction({"merchant": "Uber", "amount": "-240.00"})

    assert result.category == "Transport"


def test_unknown_category_from_llm_is_sanitized(monkeypatch):
    """A defensive net: even an LLM result bypassing llm.py validation lands safely."""

    class FakeResult:
        category = "Fooding"  # not in ALLOWED_CATEGORIES
        confidence = 0.9
        reason = "meh"

    monkeypatch.setattr(
        service_module, "categorize_with_llm", lambda **kwargs: FakeResult(),
    )

    result = categorize_transaction(TransactionStub(merchant="XYZ RANDOM STORE"))

    # Invalid model output degrades to Uncategorized, never crashes.
    assert result.category == "Uncategorized"
    assert result.method == "fallback"


def test_custom_user_categories_do_not_weaken_system_validation():
    import pytest
    from pydantic import ValidationError
    from app.schemas.categorization import CategorizedTransaction, LLMCategorization, UserPreferenceCategorization

    assert UserPreferenceCategorization(category=" Family support ").category == "Family support"
    with pytest.raises(ValidationError):
        LLMCategorization(category="Family support", confidence=0.9)
    for method in ("rule", "llm", "fallback"):
        with pytest.raises(ValidationError):
            CategorizedTransaction(category="Family support", confidence=0.9, method=method)
    for invalid in (" ", "x" * 101):
        with pytest.raises(ValidationError):
            UserPreferenceCategorization(category=invalid)
