"""Current explicit user feedback; never financial facts."""
from datetime import date, datetime, timezone
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class CoachingFeedback(Base):
    __tablename__ = "coaching_feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "recommendation_id", name="uq_coaching_feedback_user_recommendation"),
        CheckConstraint("status IN ('dismissed', 'acted_on', 'not_relevant', 'snoozed')", name="ck_coaching_feedback_status"),
        CheckConstraint("(status = 'snoozed' AND snoozed_until IS NOT NULL) OR (status <> 'snoozed' AND snoozed_until IS NULL)", name="ck_coaching_feedback_snooze"),
        Index("ix_coaching_feedback_user_status", "user_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[str] = mapped_column(String(300))
    evidence_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    snoozed_until: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
