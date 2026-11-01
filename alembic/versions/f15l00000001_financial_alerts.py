"""Create persistent user-scoped financial alerts table.

Revision ID: f15l00000001
Revises: f15g00000001
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "f15l00000001"
down_revision = "f15g00000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "financial_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_key", sa.String(120), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("title_key", sa.String(100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("message_key", sa.String(100), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "alert_key", name="uq_financial_alerts_user_key"),
        sa.CheckConstraint("status IN ('active', 'resolved', 'dismissed')", name="ck_financial_alerts_status"),
        sa.CheckConstraint("severity IN ('critical', 'high', 'medium', 'low', 'info')", name="ck_financial_alerts_severity"),
    )
    op.create_index("ix_financial_alerts_user_id", "financial_alerts", ["user_id"])
    op.create_index("ix_financial_alerts_user_status", "financial_alerts", ["user_id", "status"])
    op.create_index("ix_financial_alerts_user_read", "financial_alerts", ["user_id", "read_at"])
    op.create_index("ix_financial_alerts_user_severity", "financial_alerts", ["user_id", "severity"])


def downgrade():
    op.drop_table("financial_alerts")
