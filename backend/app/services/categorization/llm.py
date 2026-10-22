"""LLM fallback for transaction categorization.

Reuses :func:`app.services.rag.chat_model.get_chat_model` — the same
OpenAI / OpenAI-compatible client the RAG features use; never a second
client.

The model is asked for strict JSON with a category drawn from
``ALLOWED_CATEGORIES``.  The raw response is parsed defensively and
validated against :class:`app.schemas.categorization.LLMCategorization`;
any failure raises :class:`CategorizationLLMError` so the orchestrating
service can fall back to ``Uncategorized`` — malformed model output must
never reach the database.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.schemas.categorization import LLMCategorization
from app.services.categorization.categories import ALLOWED_CATEGORIES
from app.services.rag.chat_model import get_chat_model


class CategorizationLLMError(RuntimeError):
    """Raised when the LLM categorization fails or returns invalid output."""


SYSTEM_PROMPT = """\
You are a transaction categorization engine for a personal finance application.

Choose exactly one category from the allowed category list.

Allowed categories:
{categories}

Rules:
- Respond with valid JSON only. No markdown, no extra text outside the JSON.
- Pick the closest matching category. Use "Other" when nothing fits.
- Never invent categories; the category must appear in the allowed list.
- Confidence must be a number between 0 and 1.

Return JSON with exactly this shape:
{{"category": "...", "confidence": 0.0, "reason": "short justification"}}
"""


def _categories_block() -> str:
    """Deterministic, newline-separated list of allowed categories."""
    return "\n".join(sorted(ALLOWED_CATEGORIES))


def _build_messages(
    merchant: str | None,
    normalized_merchant: str | None,
    description: str | None,
    amount: str | None,
) -> list[tuple[str, str]]:
    fields: list[str] = []

    for label, value in (
        ("Merchant", merchant),
        ("Normalized merchant", normalized_merchant),
        ("Description", description),
        ("Amount", amount),
    ):
        if value:
            fields.append(f"{label}: {value}")

    # The caller should have filtered empty text out, but degrade gracefully.
    if not fields:
        fields.append("Merchant: <unknown>")

    return [
        ("system", SYSTEM_PROMPT.format(categories=_categories_block())),
        ("human", "\n".join(fields)),
    ]


def _parse_payload(text: str) -> dict[str, Any]:
    """Extract a JSON object from the model's response text."""
    cleaned = text.strip()

    # Strip a surrounding markdown code fence if present.
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fall back to the outermost {...} span for talkative models.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


def categorize_with_llm(
    *,
    merchant: str | None = None,
    normalized_merchant: str | None = None,
    description: str | None = None,
    amount: str | None = None,
) -> LLMCategorization:
    """Categorize one transaction with the chat model.

    Returns a validated :class:`LLMCategorization`, or raises
    :class:`CategorizationLLMError` for any failure: missing API key,
    transport error, malformed JSON, invalid category, or out-of-range
    confidence.
    """
    try:
        chat = get_chat_model()

        messages = _build_messages(
            merchant, normalized_merchant, description, amount,
        )
        response = chat.invoke(messages)

        content = response.content
        if not isinstance(content, str):
            content = str(content)

        payload = _parse_payload(content)
        return LLMCategorization.model_validate(payload)

    except Exception as exc:  # noqa: BLE001 - deliberately broad; see docstring
        raise CategorizationLLMError(
            f"LLM categorization failed: {exc}"
        ) from exc
