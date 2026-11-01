"""Persistent logical daily profile; historical algorithms remain immutable."""
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import Date, DateTime, ForeignKey, JSON, Numeric, String, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class FinancialHealthSnapshot(Base):
    __tablename__ = "financial_health_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", "calculation_version", name="uq_health_user_date_version"),
        CheckConstraint("overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)", name="ck_health_score"),
        CheckConstraint("coverage_percent >= 0 AND coverage_percent <= 100", name="ck_health_coverage"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(String(24))
    coverage_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    data_quality_status: Mapped[str] = mapped_column(String(16))
    schema_version: Mapped[str] = mapped_column(String(16))
    calculation_version: Mapped[str] = mapped_column(String(40))
    profile: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
