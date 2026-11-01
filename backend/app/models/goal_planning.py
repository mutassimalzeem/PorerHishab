"""Versioned intended plans and immutable user-reported progress events."""
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

def now(): return datetime.now(timezone.utc)

class GoalPlanRecord(Base):
    __tablename__ = "goal_plans"
    __table_args__ = (UniqueConstraint("user_id", "goal_id", "version", name="uq_goal_plan_version"), Index("ix_goal_plan_owner_goal", "user_id", "goal_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    goal_id: Mapped[int] = mapped_column(ForeignKey("savings_goals.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    profile: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class GoalMilestone(Base):
    __tablename__ = "goal_milestones"
    __table_args__ = (UniqueConstraint("plan_id", "sequence", name="uq_goal_milestone_sequence"),
        CheckConstraint("target_cumulative > 0 AND expected_contribution > 0", name="ck_milestone_amount"),
        CheckConstraint("status IN ('pending','missed','reported_completed')", name="ck_milestone_status"),
        Index("ix_goal_milestone_owner_goal", "user_id", "goal_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    goal_id: Mapped[int] = mapped_column(ForeignKey("savings_goals.id", ondelete="CASCADE"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("goal_plans.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date)
    target_cumulative: Mapped[Decimal] = mapped_column(Numeric(14,2))
    expected_contribution: Mapped[Decimal] = mapped_column(Numeric(14,2))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class GoalProgressEvent(Base):
    __tablename__ = "goal_progress_events"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_goal_event_request"), Index("ix_goal_event_owner_goal", "user_id", "goal_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    goal_id: Mapped[int] = mapped_column(ForeignKey("savings_goals.id", ondelete="CASCADE"))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
