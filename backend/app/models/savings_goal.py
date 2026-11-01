"""User-reported savings goals; balances are never inferred from accounts."""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Integer, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SavingsGoal(Base):
    __tablename__ = "savings_goals"
    __table_args__ = (
        CheckConstraint("target_amount > 0", name="ck_savings_goals_target"),
        CheckConstraint("current_saved IS NULL OR current_saved >= 0", name="ck_savings_goals_saved"),
        CheckConstraint("status IN ('active', 'paused', 'completed', 'cancelled')", name="ck_savings_goals_status"),
        CheckConstraint("status != 'completed' OR (current_saved IS NOT NULL AND current_saved >= target_amount)", name="ck_savings_goals_completed"),
        CheckConstraint("priority BETWEEN 1 AND 5", name="ck_goal_priority"),
        CheckConstraint("currency = 'BDT'", name="ck_goal_currency"),
        CheckConstraint("goal_type IN ('emergency_fund','purchase','savings','debt_repayment','expense_reduction','custom')", name="ck_goal_type"),
        Index("ix_savings_goals_user_status", "user_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    current_saved: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="active", nullable=False)
    goal_type: Mapped[str] = mapped_column(String(24), default="savings", server_default="savings", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BDT", server_default="BDT", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
