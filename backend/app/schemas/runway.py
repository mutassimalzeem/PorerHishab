"""Decimal runway contract, with explicit unknowns and scenario resolution."""
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel
from app.schemas.intelligence import IntelligencePeriod

RunwayMode = Literal["historical", "known_obligations"]


class RunwayCheckpoint(BaseModel):
    date: date
    projected_balance: Decimal
    minimum_balance: Decimal
    period_start: date | None = None
    forecast_income: Decimal | None = None
    forecast_expense: Decimal | None = None
    scheduled_expense_reserve: Decimal | None = None
    expected_expense_reserve: Decimal | None = None


class FinancialRunway(BaseModel):
    currency: Literal["BDT"] = "BDT"
    period: IntelligencePeriod
    mode: RunwayMode
    starting_balance: Decimal | None
    reported_balance: Decimal | None
    derived_balance: Decimal | None
    balance_source: Literal["reconciled", "derived", "reported", "mixed", "caller", "unknown"]
    known_future_income: Decimal
    scheduled_expense_reserve: Decimal
    forecast_income: Decimal | None
    forecast_expense: Decimal | None
    expected_expense_reserve: Decimal | None
    known_obligations_end_balance: Decimal | None
    projected_end_balance: Decimal | None
    minimum_projected_balance: Decimal | None
    safety_threshold: Decimal
    runway_status: Literal["positive", "at_risk", "cash_shortfall", "insufficient_data"]
    runway_days: int | None
    first_shortfall_date: date | None
    first_shortfall_period: IntelligencePeriod | None
    confidence: Literal["high", "medium", "low", "unknown"]
    checkpoints: list[RunwayCheckpoint]
    assumptions: list[str]
    limitations: list[str]
