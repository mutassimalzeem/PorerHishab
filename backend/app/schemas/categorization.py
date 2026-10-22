"""Schemas for the transaction categorization pipeline.

Two models live here:

* :class:`LLMCategorization` — the *raw* LLM answer.  It is the only
  representation of model output allowed across the pipeline boundary;
  anything the LLM returns that does not validate against it is rejected
  and the transaction stays ``Uncategorized``.
* :class:`CategorizedTransaction` — the final pipeline result (saved
  alongside the transaction as ``category``/``confidence``/.. ``method``/
  ``reason``).

Malformed model output must never reach the database, so every category
value is validated against :data:`ALLOWED_CATEGORIES` and every
confidence value must be between 0 and 1.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.categorization.categories import ALLOWED_CATEGORIES

#: How a category was decided.  ``rule`` = deterministic engine,
#: ``llm`` = model fallback, ``fallback`` = neither worked (Uncategorized).
CategorizationMethod = Literal["rule", "llm", "fallback"]


def _validate_category(value: object) -> str:
    """Strip and validate a category against the controlled vocabulary."""
    if isinstance(value, str):
        value = value.strip()
    if value not in ALLOWED_CATEGORIES:
        raise ValueError(
            f"category must be one of {sorted(ALLOWED_CATEGORIES)}, got {value!r}"
        )
    return value


class _CategoryValidation(BaseModel):
    """Shared validation for models carrying a category + confidence."""

    model_config = ConfigDict(extra="ignore")

    @field_validator("category", mode="before", check_fields=False)
    @classmethod
    def _category_must_be_allowed(cls, value: object) -> str:
        return _validate_category(value)

    @field_validator("confidence", check_fields=False)
    @classmethod
    def _confidence_between_zero_and_one(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value


class LLMCategorization(_CategoryValidation):
    """Strict view of the LLM's categorization answer."""

    category: str
    confidence: float
    reason: str | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def _clean_reason(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class CategorizedTransaction(_CategoryValidation):
    """Final categorization result for one transaction."""

    category: str
    confidence: float
    method: CategorizationMethod
    reason: str | None = None
