"""Persistent user-scoped financial alert records."""
from datetime import datetime, timezone
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class FinancialAlert(Base):
    """A persistent record of a detected financial condition and its lifecycle."""

    __tablename__ = "financial_alerts"

    __table_args__ = (
        UniqueConstraint("user_id", "alert_key", name="uq_financial_alerts_user_key"),
        CheckConstraint(
            "status IN ('active', 'resolved', 'dismissed')",
            name="ck_financial_alerts_status",
        ),
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'info')",
            name="ck_financial_alerts_severity",
        ),
        Index("ix_financial_alerts_user_status", "user_id", "status"),
        Index("ix_financial_alerts_user_read", "user_id", "read_at"),
        Index("ix_financial_alerts_user_severity", "user_id", "severity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    alert_key: Mapped[str] = mapped_column(String(120), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    title_key: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    message_key: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    last_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    actioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    occurrence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
