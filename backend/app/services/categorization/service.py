"""Categorization pipeline orchestration.

    transaction
        │
        ▼
    user preference (per-user merchant preference, when available)
        ├── matched ──► user preference result
        ▼
    rule engine (match_rules)
        ├── matched ──► rule result
        ▼
    LLM fallback (categorize_with_llm)
        ├── valid ──► LLM result
        └── invalid / unavailable ──► Uncategorized

A user's previously corrected merchant category always wins, then
deterministic rules, then AI only when necessary, with strict validation
of model output and a safe fallback.  The result always carries
``category``/``confidence``/``method``/``reason``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.repositories.transaction_repository import (
    get_merchant_category_preference,
)
from app.schemas.categorization import CategorizedTransaction, LLMCategorization
from app.services.categorization.categories import UNCATEGORIZED
from app.services.categorization.llm import CategorizationLLMError
from app.services.categorization.llm import categorize_with_llm
from app.services.categorization.merchant import normalize_merchant
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


def get_user_preference_result(
    db,
    *,
    user_id,
    merchant,
    normalized_merchant,
) -> CategorizedTransaction | None:
    """Build the categorization result for a per-user merchant preference.

    Normalizes the merchant text, looks up ``(
    user_id, normalized_merchant)`` in ``merchant_category_preferences``,
    and returns a :class:`CategorizedTransaction` on a hit — or ``None``
    when there is no preference (or no merchant to look up).
    """
    if db is None or user_id is None:
        return None

    candidate = normalize_merchant(normalized_merchant or merchant)
    if not candidate:
        return None

    preference = get_merchant_category_preference(
        db,
        user_id=int(user_id),
        normalized_merchant=candidate,
    )
    if preference is None:
        return None

    return CategorizedTransaction(
        category=preference.category,
        confidence=1.0,
        method="user_preference",
        reason=(
            f"Matched your previous preference for "
            f"{preference.normalized_merchant!r}."
        ),
    )


def categorize_transaction(
    transaction: Any,
    *,
    db: Session | None = None,
    user_id: int | None = None,
) -> CategorizedTransaction:
    """Categorize a single transaction.

    ``transaction`` may be a SQLAlchemy ``Transaction``, a schema, or a
    mapping exposing ``merchant`` / ``normalized_merchant`` /
    ``description`` (and optionally ``amount``).

    When ``db`` and ``user_id`` are provided, the user's previously
    corrected preference for this merchant is checked first and wins.
    Rules run next; on a miss the LLM fallback categorizes the
    transaction, and any LLM failure (missing API key, malformed or
    invalid output) degrades gracefully to ``Uncategorized``.
    """
    merchant = _field(transaction, "merchant")
    normalized_merchant = _field(transaction, "normalized_merchant")
    description = _field(transaction, "description")
    amount = _field(transaction, "amount")

    # 1. USER PREFERENCE — corrections made by this user take priority.
    preference = get_user_preference_result(
        db,
        user_id=user_id,
        merchant=merchant,
        normalized_merchant=normalized_merchant,
    )
    if preference is not None:
        return preference

    # 2. RULES
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

    # 3. LLM
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
