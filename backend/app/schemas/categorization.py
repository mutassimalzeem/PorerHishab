"""Schemas for the transaction categorization pipeline.

Three models live here:

* :class:`LLMCategorization` — the *raw* LLM answer.  It is the only
  representation of model output allowed across the pipeline boundary;
  anything the LLM returns that does not validate against it is rejected
  and the transaction stays ``Uncategorized``.
* :class:`CategorizedTransaction` — the final pipeline result (saved
  alongside the transaction as ``category``/``confidence``/.. ``method``/
  ``reason``).

* :class:`UserPreferenceCategorization` accepts a bounded, nonblank category
  explicitly chosen by the user, without extending the system taxonomy.

Malformed model output must never reach the database, so system-generated
category values are validated against :data:`ALLOWED_CATEGORIES` and every
confidence value must be between 0 and 1.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.categorization.categories import ALLOWED_CATEGORIES

#: How a category was decided.  ``user_preference`` = per-user merchant
#: preference, ``rule`` = deterministic engine, ``llm`` = model fallback,
#: ``fallback`` = neither worked (Uncategorized).
CategorizationMethod = Literal["user_preference", "rule", "llm", "fallback"]


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
    reason: str | None = Field(default=None, max_length=400)

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
    reason: str | None = Field(default=None, max_length=400)


class UserPreferenceCategorization(BaseModel):
    """Trusted user correction, separate from the system/LLM taxonomy boundary."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=100)
    confidence: Literal[1.0] = 1.0
    method: Literal["user_preference"] = "user_preference"
    reason: str | None = Field(default=None, max_length=400)

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value):
        return value.strip() if isinstance(value, str) else value
