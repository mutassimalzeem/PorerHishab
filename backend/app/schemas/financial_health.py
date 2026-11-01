"""Versioned observable financial condition, distinct from coverage."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field

HealthStatus = Literal["strong", "stable", "watch", "strained", "insufficient_data"]
Direction = Literal["improving", "stable", "declining", "insufficient_data"]

class FinancialHealthEvidence(BaseModel):
    metric: str
    value: Decimal | int | str
    unit: str
    source: str
    as_of_date: date
    observed_at: datetime

class FinancialHealthComponent(BaseModel):
    key: str
    score: Decimal | None = Field(None, ge=0, le=100)
    status: HealthStatus = "insufficient_data"
    data_available: bool = False
    explanation: str
    evidence: list[FinancialHealthEvidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    calculation_metadata: dict[str, str] = Field(default_factory=dict)

class FinancialHealthTrend(BaseModel):
    direction: Direction = "insufficient_data"
    change: Decimal | None = None
    period: str = "90d"
    confidence: Literal["adequate", "limited", "insufficient"] = "insufficient"
    comparison_date: date | None = None
    current_date: date | None = None
    components: dict[str, Direction] = Field(default_factory=dict)
    limitation: str = "Trends require comparable versions, coverage and at least seven days between observations."

class FinancialHealthProfile(BaseModel):
    overall_score: Decimal | None = Field(None, ge=0, le=100)
    status: HealthStatus = "insufficient_data"
    coverage_percent: Decimal = Field(Decimal("0"), ge=0, le=100)
    available_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    data_quality_status: Literal["insufficient", "limited", "partial", "good", "high"] = "insufficient"
    limitations: list[str] = Field(default_factory=list)
    components: list[FinancialHealthComponent]
    trend: FinancialHealthTrend = Field(default_factory=FinancialHealthTrend)
    schema_version: str = "1"
    calculation_version: str = "ai-15o-v1"
    as_of_date: date
    observed_at: datetime | None = None
