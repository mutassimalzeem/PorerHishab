from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TransactionCategoryCorrection(Base):
    __tablename__ = "transaction_category_corrections"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    old_category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    new_category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    old_method: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    corrected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")

    transaction = relationship("Transaction")