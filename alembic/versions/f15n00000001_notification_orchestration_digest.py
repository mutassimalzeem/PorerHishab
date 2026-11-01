"""Create notification digest tables and extend notification delivery orchestration.

Revision ID: f15n00000001
Revises: f15m00000001
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "f15n00000001"
down_revision = "f15m00000001"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Extend notification_preferences
    with op.batch_alter_table("notification_preferences") as batch_op:
        batch_op.add_column(
            sa.Column("immediate_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(
            sa.Column("daily_digest_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("daily_digest_time", sa.String(5), nullable=True, server_default="20:00")
        )

    # 2. notification_digests table
    op.create_table(
        "notification_digests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="GENERATED"),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.UniqueConstraint("user_id", "local_date", name="uq_notification_digests_user_local_date"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'GENERATED', 'PROCESSING', 'SENT', 'FAILED', 'SKIPPED')",
            name="ck_notification_digests_status",
        ),
    )
    op.create_index("ix_notification_digests_user_id", "notification_digests", ["user_id"])
    op.create_index("ix_notification_digests_user_status", "notification_digests", ["user_id", "status"])
    op.create_index("ix_notification_digests_date", "notification_digests", ["local_date"])

    # 3. notification_digest_items table
    op.create_table(
        "notification_digest_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("digest_id", sa.Integer(), sa.ForeignKey("notification_digests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("financial_alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("digest_id", "alert_id", name="uq_notification_digest_items_digest_alert"),
    )
    op.create_index("ix_notification_digest_items_digest_id", "notification_digest_items", ["digest_id"])
    op.create_index("ix_notification_digest_items_alert_id", "notification_digest_items", ["alert_id"])

    # 4. Extend notification_deliveries
    with op.batch_alter_table("notification_deliveries") as batch_op:
        batch_op.add_column(
            sa.Column("digest_id", sa.Integer(), sa.ForeignKey("notification_digests.id", ondelete="CASCADE"), nullable=True)
        )
        batch_op.add_column(
            sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.alter_column("alert_id", existing_type=sa.Integer(), nullable=True)
        batch_op.drop_constraint("ck_notification_deliveries_event", type_="check")
        batch_op.create_check_constraint(
            "ck_notification_deliveries_event",
            "notification_event IN ('ALERT_CREATED', 'ALERT_ESCALATED', 'ALERT_RECURRED', 'DAILY_DIGEST')",
        )
        batch_op.create_index("ix_notification_deliveries_digest_id", ["digest_id"])


def downgrade():
    with op.batch_alter_table("notification_deliveries") as batch_op:
        batch_op.drop_index("ix_notification_deliveries_digest_id")
        batch_op.drop_constraint("ck_notification_deliveries_event", type_="check")
        batch_op.create_check_constraint(
            "ck_notification_deliveries_event",
            "notification_event IN ('ALERT_CREATED', 'ALERT_ESCALATED', 'ALERT_RECURRED')",
        )
        batch_op.alter_column("alert_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("occurrence_count")
        batch_op.drop_column("digest_id")

    op.drop_table("notification_digest_items")
    op.drop_table("notification_digests")

    with op.batch_alter_table("notification_preferences") as batch_op:
        batch_op.drop_column("daily_digest_time")
        batch_op.drop_column("daily_digest_enabled")
        batch_op.drop_column("immediate_enabled")

