"""Persistent user-scoped notification digest models."""
from datetime import date, datetime, timezone
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class NotificationDigest(Base):
    """A persistent daily digest record aggregating multiple financial alerts for a user."""

    __tablename__ = "notification_digests"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "local_date",
            name="uq_notification_digests_user_local_date",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'GENERATED', 'PROCESSING', 'SENT', 'FAILED', 'SKIPPED')",
            name="ck_notification_digests_status",
        ),
        Index("ix_notification_digests_user_id", "user_id"),
        Index("ix_notification_digests_user_status", "user_id", "status"),
        Index("ix_notification_digests_date", "local_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="GENERATED", nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)

    items: Mapped[list["NotificationDigestItem"]] = relationship(
        "NotificationDigestItem",
        back_populates="digest",
        cascade="all, delete-orphan",
        order_by="NotificationDigestItem.id.asc()",
    )


class NotificationDigestItem(Base):
    """An individual financial alert item captured within a daily digest."""

    __tablename__ = "notification_digest_items"

    __table_args__ = (
        UniqueConstraint(
            "digest_id",
            "alert_id",
            name="uq_notification_digest_items_digest_alert",
        ),
        Index("ix_notification_digest_items_digest_id", "digest_id"),
        Index("ix_notification_digest_items_alert_id", "alert_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    digest_id: Mapped[int] = mapped_column(
        ForeignKey("notification_digests.id", ondelete="CASCADE"),
        nullable=False,
    )
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("financial_alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    digest: Mapped["NotificationDigest"] = relationship(
        "NotificationDigest",
        back_populates="items",
    )

