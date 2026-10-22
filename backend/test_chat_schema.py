"""Regression tests for the chat API schemas.

``/chat/ask`` has always returned an ``intent`` field (the hybrid query
router's decision); the response schema just did not declare it until
now.  These tests pin the contract.
"""

import pytest
from pydantic import ValidationError

from app.schemas.chat import (
    FinanceQuestionRequest,
    FinanceQuestionResponse,
)


def test_response_accepts_intent_and_sources():
    payload = FinanceQuestionResponse(
        answer="You spent 9,999 BDT on Food.",
        intent="analytics",
        sources=[{"kind": "analytics", "name": "categories"}],
    )

    assert payload.intent == "analytics"
    assert payload.answer.startswith("You spent")
    assert payload.sources == [{"kind": "analytics", "name": "categories"}]


def test_response_requires_intent():
    with pytest.raises(ValidationError):
        FinanceQuestionResponse(answer="ok", sources=[])


def test_response_requires_answer_sources_and_intent():
    with pytest.raises(ValidationError):
        FinanceQuestionResponse(answer="ok", intent="rag")

    with pytest.raises(ValidationError):
        FinanceQuestionResponse(intent="rag", sources=[])


def test_request_schema_unchanged():
    payload = FinanceQuestionRequest(question="How much did I spend on food?")

    assert payload.k == 5  # documented default from AI-05
