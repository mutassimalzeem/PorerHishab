"""Create persistent notification preferences and delivery outbox tables.

Revision ID: f15m00000001
Revises: f15l00000001
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "f15m00000001"
down_revision = "f15l00000001"
branch_labels = None
depends_on = None


def upgrade():
    # 1. notification_preferences table
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("in_app_min_severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_min_severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("quiet_hours_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("quiet_hours_start", sa.String(5), nullable=True, server_default="22:00"),
        sa.Column("quiet_hours_end", sa.String(5), nullable=True, server_default="07:00"),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Asia/Dhaka"),
        sa.Column("frequency_mode", sa.String(20), nullable=False, server_default="immediate"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_notification_preferences_user_id"),
        sa.CheckConstraint(
            "in_app_min_severity IN ('critical', 'high', 'medium', 'low', 'info', 'warning')",
            name="ck_notification_pref_in_app_min_severity",
        ),
        sa.CheckConstraint(
            "email_min_severity IN ('critical', 'high', 'medium', 'low', 'info', 'warning')",
            name="ck_notification_pref_email_min_severity",
        ),
        sa.CheckConstraint(
            "frequency_mode IN ('immediate', 'daily_digest', 'off')",
            name="ck_notification_pref_frequency_mode",
        ),
    )
    op.create_index("ix_notification_preferences_user_id", "notification_preferences", ["user_id"])

    # 2. notification_deliveries table
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("financial_alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("notification_event", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("failure_category", sa.String(30), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "alert_id",
            "channel",
            "notification_event",
            name="uq_notification_deliveries_logical_identity",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_notification_deliveries_idempotency_key",
        ),
        sa.CheckConstraint(
            "channel IN ('in_app', 'email')",
            name="ck_notification_deliveries_channel",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED', 'DEAD_LETTER', 'SUPPRESSED')",
            name="ck_notification_deliveries_status",
        ),
        sa.CheckConstraint(
            "notification_event IN ('ALERT_CREATED', 'ALERT_ESCALATED', 'ALERT_RECURRED')",
            name="ck_notification_deliveries_event",
        ),
    )
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])
    op.create_index("ix_notification_deliveries_alert_id", "notification_deliveries", ["alert_id"])
    op.create_index("ix_notification_deliveries_user_status", "notification_deliveries", ["user_id", "status"])
    op.create_index("ix_notification_deliveries_claim", "notification_deliveries", ["status", "next_attempt_at"])


def downgrade():
    op.drop_table("notification_deliveries")
    op.drop_table("notification_preferences")
