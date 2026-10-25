"""Request and response schemas for scheduled cashflow items."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CashflowKind = Literal["income", "expense"]
CashflowStatus = Literal["scheduled", "paid", "cancelled"]


class ScheduledCashflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    kind: CashflowKind
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    due_date: date
    category: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class ScheduledCashflowUpdate(ScheduledCashflowCreate):
    title: str = Field(default=None, min_length=1, max_length=160)
    kind: CashflowKind = None
    amount: Decimal = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    due_date: date = None
    status: CashflowStatus = None

    @field_validator("title", "kind", "amount", "due_date", "status", mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("field must not be null")
        return value


class ScheduledCashflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    kind: CashflowKind
    amount: Decimal
    due_date: date
    status: CashflowStatus
    category: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ScheduledCashflowPage(BaseModel):
    items: list[ScheduledCashflowRead]
    total: int
    limit: int
    offset: int
