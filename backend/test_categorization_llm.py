"""Tests for the LLM categorization fallback.

``get_chat_model`` is mocked everywhere — unit tests never make real
API calls, so the application does not depend on the free third-party
provider staying up or keeping its contract.
"""

import json
from types import SimpleNamespace

import pytest

import app.services.categorization.llm as llm_module
from app.services.categorization.llm import (
    CategorizationLLMError,
    categorize_with_llm,
)


def _stub_chat_model(response_content: str):
    chat_factory = SimpleNamespace(
        invoke=lambda _messages: SimpleNamespace(content=response_content)
    )
    return chat_factory


@pytest.fixture
def stub_llm(monkeypatch):
    """Patch ``get_chat_model`` inside the llm module; returns a recorder."""

    monkeypatch.setattr(llm_module.settings, "AI_EXTERNAL_ENABLED", True)

    def _install(response_content: str) -> dict:
        chat_model = _stub_chat_model(response_content)
        calls: list[list[tuple[str, str]]] = []

        chat_model.invoke = lambda messages: calls.append(messages) or (
            SimpleNamespace(content=response_content)
        )

        monkeypatch.setattr(llm_module, "get_chat_model", lambda: chat_model)
        return {"calls": calls}

    return _install


VALID_RESPONSE = json.dumps(
    {"category": "Groceries", "confidence": 0.96, "reason": "Supermarket purchase"}
)


def test_valid_llm_response_is_accepted(stub_llm):
    stub_llm(VALID_RESPONSE)

    result = categorize_with_llm(
        merchant="Agora",
        description="AGORA SUPERSHOP GULSHAN",
        amount="-2350.00",
    )

    assert result.category == "Groceries"
    assert result.confidence == 0.96
    assert result.reason == "Supermarket purchase"


def test_prompt_contains_allowed_categories_and_transaction(stub_llm):
    installed = stub_llm(VALID_RESPONSE)

    categorize_with_llm(
        merchant="Agora", description="AGORA SUPERSHOP GULSHAN", amount=-2350.00,
    )

    (messages,) = installed["calls"]
    system_prompt = messages[0][1]
    user_prompt = messages[1][1]

    for expected in ("Groceries", "Uncategorized", "Transport", "Subscription"):
        assert expected in system_prompt
    assert "Merchant: Agora" in user_prompt
    assert "AGORA SUPERSHOP GULSHAN" in user_prompt
    assert "Amount: -2350.0" in user_prompt


def test_json_inside_markdown_fence_is_parsed(stub_llm):
    stub_llm("```json\n" + VALID_RESPONSE + "\n```")

    result = categorize_with_llm(merchant="Agora")

    assert result.category == "Groceries"


def test_json_surrounded_by_chatter_is_parsed(stub_llm):
    stub_llm(
        "Here is my answer: " + VALID_RESPONSE + " Hope that helps!"
    )

    result = categorize_with_llm(merchant="Agora")

    assert result.category == "Groceries"


def test_invented_category_is_rejected(stub_llm):
    stub_llm(
        json.dumps({"category": "Food & Lifestyle", "confidence": 0.9, "reason": "x"})
    )

    with pytest.raises(CategorizationLLMError):
        categorize_with_llm(merchant="Agora")


def test_confidence_above_one_is_rejected(stub_llm):
    stub_llm(json.dumps({"category": "Food", "confidence": 1.5, "reason": "x"}))

    with pytest.raises(CategorizationLLMError):
        categorize_with_llm(merchant="Foodpanda")


def test_confidence_below_zero_is_rejected(stub_llm):
    stub_llm(json.dumps({"category": "Food", "confidence": -0.2, "reason": "x"}))

    with pytest.raises(CategorizationLLMError):
        categorize_with_llm(merchant="Foodpanda")


def test_malformed_json_is_rejected(stub_llm):
    stub_llm("The category is Groceries, obviously. No JSON here.")

    with pytest.raises(CategorizationLLMError):
        categorize_with_llm(merchant="Agora")


def test_plain_text_inside_fence_without_braces_is_rejected(stub_llm):
    stub_llm("```\nGroceries, high confidence\n```")

    with pytest.raises(CategorizationLLMError):
        categorize_with_llm(merchant="Agora")


def test_missing_category_is_rejected(stub_llm):
    stub_llm(json.dumps({"confidence": 0.9}))

    with pytest.raises(CategorizationLLMError):
        categorize_with_llm(merchant="Agora")


def test_transport_error_is_wrapped(monkeypatch):
    monkeypatch.setattr(llm_module.settings, "AI_EXTERNAL_ENABLED", True)
    def broken_chat_model():
        raise RuntimeError("provider is down")

    monkeypatch.setattr(llm_module, "get_chat_model", broken_chat_model)

    with pytest.raises(CategorizationLLMError):
        categorize_with_llm(merchant="Agora")
