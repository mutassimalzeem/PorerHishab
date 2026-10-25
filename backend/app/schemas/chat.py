from datetime import date
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.schemas.coach import Money, PositiveMoney


class FinanceQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date | None = None
    end_date: date | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    purchase_amount: PositiveMoney | None = None
    starting_balance: Money | None = None
    safety_buffer: Money | None = None

    @field_validator("question", check_fields=False)
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()

    question: str = Field(min_length=1, max_length=1000)
    k: int = Field(default=5, ge=1, le=10)


class FinanceQuestionResponse(BaseModel):
    answer: str
    intent: str
    sources: list[dict]
    calculation: dict[str, Any] = Field(default_factory=dict)
    date_range: dict[str, str] | None = None
    coverage: dict[str, Any] | None = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    status: str = "answered"
