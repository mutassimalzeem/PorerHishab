"""accounts
--------
id
user_id
name
source
account_type
currency
created_at"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    account_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="cash",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="BDT",
    )

    current_balance: Mapped[float | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="accounts",
    )

    transactions = relationship(
        "Transaction",
        back_populates="account",
        cascade="all, delete-orphan",
    )