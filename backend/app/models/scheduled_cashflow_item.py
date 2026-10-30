
"""Planned income and expense events that have not necessarily occurred."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScheduledCashflowItem(Base):
    """A user-owned, dated expectation of future income or expense."""

    __tablename__ = "scheduled_cashflow_items"

    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_scheduled_cashflow_item_id_user"),
        CheckConstraint(
            "amount > 0",
            name="ck_scheduled_cashflow_items_amount_positive",
        ),
        CheckConstraint(
            "kind IN ('income', 'expense')",
            name="ck_scheduled_cashflow_items_kind",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'paid', 'cancelled')",
            name="ck_scheduled_cashflow_items_status",
        ),
        Index(
            "ix_scheduled_cashflow_user_due_date",
            "user_id",
            "due_date",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False)

    title: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )

    due_date: Mapped[date] = mapped_column(
        Date,
        nullable=False)

    status: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        default="scheduled",
    )

    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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

    user = relationship("User")
