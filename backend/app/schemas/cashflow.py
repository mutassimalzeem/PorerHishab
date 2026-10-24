from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class CashflowMonth(BaseModel):
    month: str
    projected_income: Decimal
    projected_expenses: Decimal
    projected_net: Decimal
    projected_balance: Decimal


class CashflowForecast(BaseModel):
    starting_balance: Decimal
    average_monthly_income: Decimal
    average_monthly_expenses: Decimal
    average_monthly_net: Decimal
    months_ahead: int = Field(ge=1, le=12)
    projected_months: list[CashflowMonth]
    cash_depletion_date: date | None
    status: str