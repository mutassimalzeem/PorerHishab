"""Request/response schemas for the transaction intelligence API.

All monetary values are handled as :class:`decimal.Decimal` to avoid binary
floating point drift.  Pydantic v2 serialises ``Decimal`` in JSON mode without
loss of precision (as a JSON string), so responses stay money-safe.
"""

from datetime import date as Date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransactionBase(BaseModel):
    """Fields shared by transaction create and update payloads."""

    date: Date = Field(..., description="Transaction/posting date.")
    amount: Decimal = Field(
        ...,
        max_digits=14,
        decimal_places=2,
        description="Signed monetary amount. Negative for expenses, positive for income.",
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Free-form description of the transaction.",
    )
    merchant: str | None = Field(
        default=None,
        max_length=255,
        description="Raw merchant name as reported by the source.",
    )
    category: str | None = Field(
        default=None,
        max_length=100,
        description="Transaction category. Auto-assigned when omitted.",
    )
    subcategory: str | None = Field(default=None, max_length=100)
    fee: Decimal = Field(default=Decimal("0.00"), max_digits=14, decimal_places=2)
    balance: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    account_id: int | None = Field(default=None, ge=1)
    trx_id: str | None = Field(default=None, max_length=100)
    transaction_type: str | None = Field(default=None, max_length=50)
    source: str | None = Field(default=None, max_length=50)
    is_recurring: bool = False
    raw_data: dict[str, Any] | None = None

    @field_validator("date")
    @classmethod
    def _reject_impossible_dates(cls, value: Date) -> Date:
        if value.year < 1900:
            raise ValueError("date must not be earlier than 1900-01-01")
        return value

    @field_validator("fee", "balance", "amount", mode="before")
    @classmethod
    def _coerce_decimal(cls, value: Any) -> Any:
        if value is None or isinstance(value, Decimal):
            return value
        if isinstance(value, bool):
            raise ValueError("boolean is not a valid monetary value")
        if isinstance(value, (int, float, str)):
            return str(value)
        raise ValueError("invalid monetary value")

    @field_validator("merchant", "description", "category", "subcategory", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("trx_id", mode="before")
    @classmethod
    def _normalize_trx_id(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class TransactionCreate(TransactionBase):
    """Payload for creating a single transaction."""

    category: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Optional explicit category. When omitted the rule-based "
            "categorizer derives one from merchant/description."
        ),
    )


class TransactionUpdate(BaseModel):
    """Payload for a partial update of a transaction."""

    date: Date | None = None
    amount: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    description: str | None = Field(default=None, max_length=2000)
    merchant: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    subcategory: str | None = Field(default=None, max_length=100)
    fee: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    balance: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    account_id: int | None = Field(default=None, ge=1)
    trx_id: str | None = Field(default=None, max_length=100)
    transaction_type: str | None = Field(default=None, max_length=50)
    source: str | None = Field(default=None, max_length=50)
    is_recurring: bool | None = None
    raw_data: dict[str, Any] | None = None

    @field_validator("date")
    @classmethod
    def _reject_impossible_dates(cls, value: Date | None) -> Date | None:
        if value is not None and value.year < 1900:
            raise ValueError("date must not be earlier than 1900-01-01")
        return value

    @field_validator("fee", "balance", "amount", mode="before")
    @classmethod
    def _coerce_decimal(cls, value: Any) -> Any:
        if value is None or isinstance(value, Decimal):
            return value
        if isinstance(value, bool):
            raise ValueError("boolean is not a valid monetary value")
        if isinstance(value, (int, float, str)):
            return str(value)
        raise ValueError("invalid monetary value")

    @field_validator("merchant", "description", "category", "subcategory", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class TransactionRead(BaseModel):
    """A transaction as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    account_id: int | None = None
    trx_id: str | None = None
    date: Date
    description: str | None = None
    merchant: str | None = None
    normalized_merchant: str | None = None
    amount: Decimal
    fee: Decimal
    balance: Decimal | None = None
    transaction_type: str | None = None
    category: str | None = None
    
    category_confidence: Decimal | None = None
    category_method: str | None = None
    category_reason: str | None = None

    subcategory: str | None = None
    source: str | None = None
    is_recurring: bool
    raw_data: dict[str, Any] | None = None
    created_at: datetime


class TransactionPage(BaseModel):
    """Paginated collection of transactions."""

    items: list[TransactionRead]
    total: int = Field(..., ge=0, description="Total rows matching the filter.")
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
    has_more: bool = Field(
        ...,
        description="True when more rows exist beyond the current page.",
    )

    @property
    def count(self) -> int:
        """Number of items in this page."""
        return len(self.items)


class TransactionList(BaseModel):
    """Plain (non-paginated) collection of transactions."""

    items: list[TransactionRead]
    count: int = Field(..., ge=0)
