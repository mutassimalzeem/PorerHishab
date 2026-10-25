from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CashflowMonth(BaseModel):
    month: str
    projected_income: Decimal
    projected_expenses: Decimal
    projected_net: Decimal
    projected_balance: Decimal


class CashflowForecast(BaseModel):
    starting_balance: Decimal
    forecast_anchor_date: date

    history_start_month: str | None
    history_end_month: str | None
    historical_months_count: int = Field(ge = 0)
    months_with_activity: int = Field(ge = 0)


    average_monthly_income: Decimal
    average_monthly_expenses: Decimal
    average_monthly_net: Decimal


    months_ahead: int = Field(ge=1, le=12)
    forecast_start_month: str
    projected_months: list[CashflowMonth]
    cash_depletion_date: date | None

    status: Literal["healthy",
                    "break_even",
                    "at_risk",
                    "insufficient_data"]
    assumptions: list[str]