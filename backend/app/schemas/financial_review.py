"""Read-only envelope retaining the canonical AI-16 contracts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict
from app.schemas.financial_plan import FinancialPlan, FinancialDecisionSet
from app.schemas.financial_execution import FinancialExecutionPlan


class FinancialReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["review_only"] = "review_only"
    requires_user_confirmation: Literal[True] = True
    schedules_confirmed: bool
    plan: FinancialPlan
    decisions: FinancialDecisionSet
    execution_plan: FinancialExecutionPlan
