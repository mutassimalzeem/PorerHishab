from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.services.finance.coach import today_dhaka


class SavingsRecommendation(BaseModel):
    category: str
    monthly_spending: Decimal
    suggested_cut: Decimal


class SavingsPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_amount: Decimal = Field(gt=0)
    current_saved: Decimal = Field(default=Decimal("0"), ge=0)
    target_date: date

    @field_validator("target_date")
    @classmethod
    def future_target(cls, value):
        if value < today_dhaka():
            raise ValueError("target_date cannot be in the past")
        return value


class SavingsPlanResponse(BaseModel):
    goal_amount: Decimal
    current_saved: Decimal
    remaining_goal: Decimal
    target_date: date
    months_remaining: int

    required_monthly_saving: Decimal

    estimated_monthly_income: Decimal | None
    estimated_monthly_spending: Decimal | None
    estimated_monthly_surplus: Decimal | None

    recommended_monthly_cut: Decimal
    projected_monthly_saving: Decimal | None

    status: str

    recommendations: list[SavingsRecommendation]
    historical_transaction_count: int = 0
    limitations: list[str] = Field(default_factory=list)