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


def test_categorization_budget_unit():
    from app.services.categorization.budget import CategorizationBudget

    budget = CategorizationBudget(max_calls=2)
    assert budget.remaining == 2
    assert budget.can_call() is True

    assert budget.consume() is True
    assert budget.remaining == 1
    assert budget.calls_used == 1
    assert budget.can_call() is True

    assert budget.consume() is True
    assert budget.remaining == 0
    assert budget.calls_used == 2
    assert budget.can_call() is False

    assert budget.consume() is False
    assert budget.remaining == 0
    assert budget.calls_used == 2


def test_categorize_with_llm_consumes_budget_at_provider_boundary(monkeypatch):
    from unittest.mock import MagicMock
    from app.core.config import settings
    from app.services.categorization.budget import CategorizationBudget
    import app.services.categorization.llm as llm_module

    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", True)

    provider_calls = 0

    class MockChat:
        def invoke(self, messages):
            nonlocal provider_calls
            provider_calls += 1
            mock_res = MagicMock()
            mock_res.content = '{"category": "Other", "confidence": 0.5, "reason": "Test"}'
            return mock_res

    monkeypatch.setattr(llm_module, "get_chat_model", lambda: MockChat())

    budget = CategorizationBudget(max_calls=1)
    res = llm_module.categorize_with_llm(
        merchant="Unknown Store",
        description="Random charge",
        budget=budget,
    )
    assert res.category == "Other"
    assert provider_calls == 1
    assert budget.calls_used == 1
    assert budget.remaining == 0

    # Second call with exhausted budget should raise CategorizationLLMError without calling provider
    import pytest
    with pytest.raises(llm_module.CategorizationLLMError):
        llm_module.categorize_with_llm(
            merchant="Unknown Store 2",
            description="Random charge 2",
            budget=budget,
        )
    assert provider_calls == 1  # provider was not invoked again
