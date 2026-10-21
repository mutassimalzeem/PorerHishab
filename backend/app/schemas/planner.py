from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class SavingsRecommendation(BaseModel):
    category: str
    monthly_spending: Decimal
    suggested_cut: Decimal


class SavingsPlanRequest(BaseModel):
    goal_amount: Decimal = Field(gt=0)
    current_saved: Decimal = Field(default=Decimal("0"), ge=0)
    target_date: date


class SavingsPlanResponse(BaseModel):
    goal_amount: Decimal
    current_saved: Decimal
    remaining_goal: Decimal
    target_date: date
    months_remaining: int

    required_monthly_saving: Decimal

    estimated_monthly_income: Decimal
    estimated_monthly_spending: Decimal
    estimated_monthly_surplus: Decimal

    recommended_monthly_cut: Decimal
    projected_monthly_saving: Decimal

    status: str

    recommendations: list[SavingsRecommendation]