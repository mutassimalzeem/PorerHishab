"""Persistent user-scoped notification preferences."""
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class NotificationPreference(Base):
    """User-scoped notification preferences controlling delivery channels and policies."""

    __tablename__ = "notification_preferences"

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_notification_preferences_user_id"),
        CheckConstraint(
            "in_app_min_severity IN ('critical', 'high', 'medium', 'low', 'info', 'warning')",
            name="ck_notification_pref_in_app_min_severity",
        ),
        CheckConstraint(
            "email_min_severity IN ('critical', 'high', 'medium', 'low', 'info', 'warning')",
            name="ck_notification_pref_email_min_severity",
        ),
        CheckConstraint(
            "frequency_mode IN ('immediate', 'daily_digest', 'off')",
            name="ck_notification_pref_frequency_mode",
        ),
        Index("ix_notification_preferences_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # In-app notifications
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    in_app_min_severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)

    # Email notifications (Conservative defaults: disabled, consent required)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    email_min_severity: Mapped[str] = mapped_column(String(20), default="warning", nullable=False)

    # Quiet hours
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quiet_hours_start: Mapped[str | None] = mapped_column(String(5), default="22:00", nullable=True)
    quiet_hours_end: Mapped[str | None] = mapped_column(String(5), default="07:00", nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Dhaka", nullable=False)

    # Frequency mode
    frequency_mode: Mapped[str] = mapped_column(String(20), default="immediate", nullable=False)

    # Timestamps
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

    def __init__(self, **kwargs):
        kwargs.setdefault("in_app_enabled", True)
        kwargs.setdefault("in_app_min_severity", "info")
        kwargs.setdefault("email_enabled", False)
        kwargs.setdefault("email_consent", False)
        kwargs.setdefault("email_consent_at", None)
        kwargs.setdefault("email_min_severity", "warning")
        kwargs.setdefault("quiet_hours_enabled", False)
        kwargs.setdefault("quiet_hours_start", "22:00")
        kwargs.setdefault("quiet_hours_end", "07:00")
        kwargs.setdefault("timezone", "Asia/Dhaka")
        kwargs.setdefault("frequency_mode", "immediate")
        super().__init__(**kwargs)
