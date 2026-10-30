"""Public, typed presentation of AI-13; no arithmetic is performed here."""
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel
from app.schemas.cashflow import CashflowForecast
from app.schemas.insights import RecurringInsight

class IntelligencePeriod(BaseModel):
    kind: str
    start: date
    end: date
    is_complete: bool
    label: str

class IntelligenceCoverage(BaseModel):
    period: IntelligencePeriod
    as_of: date
    months_expected_complete: int
    complete_months_observed: list[str]
    partial_months_observed: list[str]
    months_observed: list[str]
    status: Literal['no_records', 'partial_current_only', 'insufficient_history', 'adequate_history']
    is_adequate: bool
    limitations: list[str]

class ObservedCategory(BaseModel):
    category: str
    expenses: Decimal
    transaction_count: int

class PlannedObservation(BaseModel):
    scheduled_item_id: int
    title: str
    kind: Literal['expense', 'income']
    amount: Decimal
    due_date: date
    record_type: Literal['plan']
    original_amount: Decimal | None = None
    allocated_amount: Decimal | None = None
    remaining_amount: Decimal | None = None

class ObligationObservation(BaseModel):
    period: IntelligencePeriod
    scheduled_expenses: Decimal
    uncertain_scheduled_income: Decimal
    items: list[PlannedObservation]
    limitations: list[str]

class HistoryObservation(BaseModel):
    period: IntelligencePeriod
    adequate: bool
    baseline: CashflowForecast | None

class GoalObservation(BaseModel):
    goal_id: int
    name: str
    target_amount: Decimal
    current_saved: Decimal | None
    target_date: date
    status: Literal['active', 'completed', 'cancelled']

class IntelligenceSnapshot(BaseModel):
    as_of_date: date
    period: IntelligencePeriod
    data_coverage: IntelligenceCoverage
    current_period_coverage: IntelligenceCoverage
    income: Decimal | None
    expenses: Decimal | None
    net_cashflow: Decimal | None
    value_kind: Literal['observed']
    category_spending: list[ObservedCategory]
    recurring_patterns: list[RecurringInsight]
    scheduled_cashflow_available: bool
    scheduled_obligations: ObligationObservation
    history: HistoryObservation
    goals: list[GoalObservation]
    limitations: list[str]

class IntelligenceCashflow(BaseModel):
    type: Literal['forecast']
    as_of_date: date
    actual_window: IntelligencePeriod
    actual_income: Decimal | None
    actual_expense: Decimal | None
    scheduled_horizon: IntelligencePeriod
    scheduled_expense: Decimal
    scheduled_income: Decimal
    forecast_income: Decimal | None
    forecast_expense: Decimal | None
    forecast_net: Decimal | None
    forecast_status: str | None
    estimated: bool
    assumptions: list[str]
    limitations: list[str]

class IntelligenceSignal(BaseModel):
    signal_type: Literal['unusual_spending', 'savings_opportunity', 'upcoming_expense', 'projected_shortfall', 'goal_progress']
    severity: Literal['info', 'warning', 'critical']
    stable_id: str
    subject: str | None
    observed_period: IntelligencePeriod
    comparison_period: IntelligencePeriod | None
    observed_value: Decimal | None
    reference_value: Decimal | None
    delta: Decimal | None
    percentage_change: Decimal | None
    estimate: bool
    estimate_label: Literal['observed', 'estimate']
    evidence: dict[str, Any]
    assumptions: list[str]
    limitations: list[str]

class CategoryComparison(BaseModel):
    category: str
    observed_period: IntelligencePeriod
    observed_expenses: Decimal
    observed_transactions: int
    comparison_period: IntelligencePeriod | None
    comparison_expenses: Decimal | None
    delta: Decimal | None
    percentage_change: Decimal | None

class MonthlyObservation(BaseModel):
    month: str
    income: Decimal | None
    expenses: Decimal | None
    net: Decimal | None
    transaction_count: int

class IntelligenceResponse(BaseModel):
    as_of_date: date
    snapshot: IntelligenceSnapshot
    cashflow: IntelligenceCashflow
    signals: list[IntelligenceSignal]
    limitations: list[str]
    category_comparisons: list[CategoryComparison]
    monthly_history: list[MonthlyObservation]
