"""Confirmed allocations; revoked rows retain the reconciliation history."""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class ObligationAllocation(Base):
    __tablename__ = "obligation_allocations"
    __table_args__ = (
        ForeignKeyConstraint(["item_id", "user_id"], ["scheduled_cashflow_items.id", "scheduled_cashflow_items.user_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["transaction_id", "user_id"], ["transactions.id", "transactions.user_id"], ondelete="RESTRICT"),
        CheckConstraint("amount > 0", name="ck_obligation_allocation_positive"),
        Index("ix_obligation_allocation_user_item", "user_id", "item_id"),
        Index("uq_obligation_active_transaction", "transaction_id", unique=True,
              postgresql_where=text("active"), sqlite_where=text("active = 1")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(nullable=False)
    item_id: Mapped[int] = mapped_column(nullable=False)
    transaction_id: Mapped[int] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
