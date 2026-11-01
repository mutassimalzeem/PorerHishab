"""Strict what-if inputs. Amount adjustments are signed deltas; goal amounts are replacements."""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.goal_planning import Key

ChangeType = Literal["income_adjustment", "recurring_expense_adjustment", "one_time_expense", "one_time_income", "savings_contribution_adjustment", "goal_target_date_adjustment", "goal_target_amount_adjustment", "goal_commitment_adjustment"]
class ScenarioChange(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    change_type: ChangeType
    amount: Decimal | None = Field(None, max_digits=14, decimal_places=2)
    percentage: Decimal | None = Field(None, ge=-100, le=1000, decimal_places=2)
    currency: Literal["BDT"] = "BDT"
    effective_date: date
    end_date: date | None = None
    frequency: Literal["monthly"] | None = None
    target_id: int | None = Field(None, gt=0)
    target_date: date | None = None
    description: str = Field("", max_length=500)

    @model_validator(mode="after")
    def valid(self):
        if self.percentage is not None and self.change_type!="income_adjustment": raise ValueError("Percentage is supported only for income adjustments")
        goal=self.change_type.startswith("goal_")
        dated=self.change_type=="goal_target_date_adjustment"
        recurring=self.change_type in {"income_adjustment","recurring_expense_adjustment","savings_contribution_adjustment"}
        if goal != (self.target_id is not None): raise ValueError("Goal changes require an owned target_id; other changes must omit it")
        if dated:
            if self.target_date is None or self.amount is not None: raise ValueError("Date changes require target_date and no amount")
        elif self.percentage is not None:
            if self.change_type!="income_adjustment" or self.amount is not None or self.target_date is not None: raise ValueError("Percentage is supported only for income adjustments without amount")
        elif self.amount is None or self.target_date is not None: raise ValueError("Amount changes require amount and no target_date")
        if self.change_type in {"one_time_expense","one_time_income","goal_target_amount_adjustment"} and self.amount<=0: raise ValueError("Amount must be positive")
        if self.change_type=="goal_commitment_adjustment" and self.amount<0: raise ValueError("Commitment cannot be negative")
        if recurring != (self.frequency=="monthly"): raise ValueError("Recurring changes require monthly frequency; other changes must omit it")
        if self.end_date is not None and (not recurring or self.end_date<self.effective_date): raise ValueError("Invalid recurring end date")
        return self

class ScenarioCreate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name: str = Field(min_length=1,max_length=120)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        return " ".join(value.split()) if isinstance(value,str) else value

    description: str = Field("",max_length=1000)

class ChangesRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    changes: list[ScenarioChange] = Field(max_length=50)

class SimulationRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    idempotency_key: Key
    schedules_confirmed: bool=False
    horizon_days: int=Field(120,ge=1,le=366)

class ScenarioRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: int
    user_id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    saved_at: datetime | None = None
    archived_at: datetime | None = None
    source_scenario_id: int | None = None
    latest_run_id: int | None = None
    latest_run_at: datetime | None = None
    result_revision: int | None = None
    result_calculation_version: str | None = None
    result_state: Literal["missing", "current", "stale"] = "missing"
    base_snapshot_reference: str | None
    status: Literal["draft","saved","archived"]
    calculation_version: str
    revision: int
    changes: list[ScenarioChange]

    @field_validator("created_at","updated_at","saved_at","archived_at","latest_run_at")
    @classmethod
    def utc_timestamps(cls,value):
        return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value

class MetricComparison(BaseModel):
    metric: str
    baseline_value: Decimal | None
    scenario_value: Decimal | None
    absolute_delta: Decimal | None
    percentage_delta: Decimal | None
    percentage_status: Literal["available","zero_baseline","not_meaningful","insufficient_data"]
    direction: Literal["increased","decreased","unchanged","unknown"]
    status: Literal["available","insufficient_data","not_available_for_scenario"]
    reason: str | None=None

class ScenarioResult(BaseModel):
    run_id: int | None=None
    scenario_id: int
    calculation_version: str
    baseline_snapshot_date: date
    baseline_snapshot_reference: str
    horizon_end: date
    comparisons: list[MetricComparison]
    baseline_goals: list[dict]
    scenario_goals: list[dict]
    assumptions: list[ScenarioChange]
    limitations: list[str]
    affordability: Literal["affordable","affordable_with_adjustments","not_affordable","insufficient_data"] | None=None
    explanation: str="This is a scenario based on the assumptions you selected, not a guaranteed future outcome."


class ScenarioMetadataUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name: str | None=Field(None,min_length=1,max_length=120)
    description: str | None=Field(None,max_length=1000)

    @field_validator("name",mode="before")
    @classmethod
    def normalize_name(cls,value):
        return " ".join(value.split()) if isinstance(value,str) else value

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set or any(getattr(self,k) is None for k in self.model_fields_set):
            raise ValueError("Supply a non-null name or description; use an empty description to clear it")
        return self

class ScenarioLibraryPage(BaseModel):
    items: list[ScenarioRead]
    total: int
    limit: int
    offset: int

class ScenarioCompareRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    scenario_ids: list[int]=Field(min_length=2,max_length=5)

    @field_validator("scenario_ids")
    @classmethod
    def distinct_positive(cls,values):
        if len(set(values))!=len(values) or any(v<=0 for v in values):raise ValueError("Select two to five distinct positive scenario IDs")
        return values

class AssumptionComparison(BaseModel):
    change: ScenarioChange
    shared: bool

class ScenarioCompareColumn(BaseModel):
    scenario: ScenarioRead
    result: ScenarioResult | None
    assumptions: list[AssumptionComparison]

class ScenarioMetricCell(BaseModel):
    scenario_id: int
    comparison: MetricComparison | None
    status: Literal["available","insufficient_data","not_available_for_scenario"]
    reason: str | None=None

class ScenarioMetricRow(BaseModel):
    metric: str
    cells: list[ScenarioMetricCell]

class ScenarioLibraryComparison(BaseModel):
    columns: list[ScenarioCompareColumn]
    metrics: list[ScenarioMetricRow]
    calculation_version: str | None
    warnings: list[Literal["different_baselines","different_snapshot_dates","different_horizons","different_schedule_confirmations","missing_results","stale_results"]]
    explanation: str="This is a scenario based on the assumptions you selected, not a guaranteed future outcome."
