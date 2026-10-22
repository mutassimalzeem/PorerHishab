"""Categorization pipeline orchestration.

    transaction
        │
        ▼
    rule engine (match_rules)
        ├── matched ──► rule result
        ▼
    LLM fallback (categorize_with_llm)
        ├── valid ──► LLM result
        └── invalid / unavailable ──► Uncategorized

Deterministic rules first, AI only when necessary, strict validation of
model output, and a safe fallback.  The result always carries
``category``/``confidence``/``method``/``reason``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from app.schemas.categorization import CategorizedTransaction, LLMCategorization
from app.services.categorization.categories import UNCATEGORIZED
from app.services.categorization.llm import CategorizationLLMError
from app.services.categorization.llm import categorize_with_llm
from app.services.categorization.rules import match_rules

logger = logging.getLogger(__name__)


def _field(transaction: Any, name: str) -> str | None:
    """Read a text field from an object (or dict) transaction, or ``None``."""
    value = (
        transaction.get(name)
        if isinstance(transaction, dict)
        else getattr(transaction, name, None)
    )

    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _fallback_result(reason: str) -> CategorizedTransaction:
    return CategorizedTransaction(
        category=UNCATEGORIZED,
        confidence=0.0,
        method="fallback",
        reason=reason,
    )


def _result_from_llm(result: LLMCategorization) -> CategorizedTransaction:
    return CategorizedTransaction(
        category=result.category,
        confidence=result.confidence,
        method="llm",
        reason=result.reason,
    )


def categorize_transaction(transaction: Any) -> CategorizedTransaction:
    """Categorize a single transaction.

    ``transaction`` may be a SQLAlchemy ``Transaction``, a schema, or a
    mapping exposing ``merchant`` / ``normalized_merchant`` /
    ``description`` (and optionally ``amount``).

    Rules run first; on a miss the LLM fallback categorizes the
    transaction, and any LLM failure (missing API key, malformed or
    invalid output) degrades gracefully to ``Uncategorized``.
    """
    merchant = _field(transaction, "merchant")
    normalized_merchant = _field(transaction, "normalized_merchant")
    description = _field(transaction, "description")
    amount = _field(transaction, "amount")

    rule_hit = match_rules(
        merchant=merchant,
        normalized_merchant=normalized_merchant,
        description=description,
    )
    if rule_hit:
        return CategorizedTransaction(**rule_hit)

    # Nothing to classify on — no point spending an LLM call.
    if not (merchant or normalized_merchant or description):
        return _fallback_result("No merchant or description text available.")

    try:
        result = categorize_with_llm(
            merchant=merchant,
            normalized_merchant=normalized_merchant,
            description=description,
            amount=amount,
        )
        return _result_from_llm(result)
    except (CategorizationLLMError, ValidationError) as exc:
        logger.warning("LLM categorization failed, falling back: %s", exc)
        return _fallback_result(
            f"LLM categorization failed or returned invalid output: {exc}"
        )

    return _result_from_llm(result)
