"""Typed scenario assumptions and immutable, versioned comparison rows."""
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Scenario(Base):
    __tablename__="financial_scenarios"
    __table_args__=(CheckConstraint("status IN ('draft','saved','archived')",name="ck_scenario_status"),)
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    name: Mapped[str]=mapped_column(String(120))
    description: Mapped[str]=mapped_column(String(1000),default="")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    base_snapshot_reference: Mapped[str | None]=mapped_column(String(64))
    status: Mapped[str]=mapped_column(String(16),default="draft")
    calculation_version: Mapped[str]=mapped_column(String(32),default="ai-15q-v1")
    revision: Mapped[int]=mapped_column(Integer,default=1)

class ScenarioChangeRecord(Base):
    __tablename__="scenario_changes"
    id: Mapped[int]=mapped_column(primary_key=True)
    scenario_id: Mapped[int]=mapped_column(ForeignKey("financial_scenarios.id",ondelete="CASCADE"),index=True)
    change_type: Mapped[str]=mapped_column(String(40))
    amount: Mapped[Decimal | None]=mapped_column(Numeric(14,2))
    percentage: Mapped[Decimal | None]=mapped_column(Numeric(7,2))
    currency: Mapped[str]=mapped_column(String(3))
    effective_date: Mapped[date]=mapped_column(Date)
    end_date: Mapped[date | None]=mapped_column(Date)
    frequency: Mapped[str | None]=mapped_column(String(12))
    target_id: Mapped[int | None]=mapped_column(Integer)
    target_date: Mapped[date | None]=mapped_column(Date)
    description: Mapped[str]=mapped_column(String(500))

class ScenarioRun(Base):
    __tablename__="scenario_runs"
    __table_args__=(UniqueConstraint("user_id","idempotency_key",name="uq_scenario_run_request"),)
    id: Mapped[int]=mapped_column(primary_key=True)
    scenario_id: Mapped[int]=mapped_column(ForeignKey("financial_scenarios.id",ondelete="CASCADE"),index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"))
    idempotency_key: Mapped[str]=mapped_column(String(80))
    request: Mapped[dict]=mapped_column(JSON)
    calculation_version: Mapped[str]=mapped_column(String(32))
    baseline_snapshot_date: Mapped[date]=mapped_column(Date)
    baseline_snapshot_reference: Mapped[str]=mapped_column(String(64))
    evidence: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class ScenarioComparison(Base):
    __tablename__="scenario_comparisons"
    __table_args__=(UniqueConstraint("run_id","metric",name="uq_scenario_run_metric"),)
    id: Mapped[int]=mapped_column(primary_key=True)
    run_id: Mapped[int]=mapped_column(ForeignKey("scenario_runs.id",ondelete="CASCADE"),index=True)
    metric: Mapped[str]=mapped_column(String(80))
    baseline_value: Mapped[Decimal | None]=mapped_column(Numeric(18,2))
    scenario_value: Mapped[Decimal | None]=mapped_column(Numeric(18,2))
    absolute_delta: Mapped[Decimal | None]=mapped_column(Numeric(18,2))
    percentage_delta: Mapped[Decimal | None]=mapped_column(Numeric(24,2))
    percentage_status: Mapped[str]=mapped_column(String(24))
    direction: Mapped[str]=mapped_column(String(16))
    status: Mapped[str]=mapped_column(String(40))
    reason: Mapped[str | None]=mapped_column(String(500))
