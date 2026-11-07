"""Recoverable, fenced notification delivery claims; preserve legacy states."""
from alembic import op
import sqlalchemy as sa

revision = "f17g00000001"
down_revision = "f17f00000001"
branch_labels = None
depends_on = None


def upgrade():
    # AI-15N added occurrence-aware keys but left this older constraint behind.
    # It incorrectly rejects a second legitimate recurrence of the same alert.
    op.drop_constraint("uq_notification_deliveries_logical_identity", "notification_deliveries", type_="unique")
    op.create_unique_constraint("uq_notification_deliveries_occurrence", "notification_deliveries",
                                ["user_id", "alert_id", "channel", "notification_event", "occurrence_count"])
    op.add_column("notification_deliveries", sa.Column("claim_token", sa.String(36), nullable=True))
    op.add_column("notification_deliveries", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_notification_deliveries_lease", "notification_deliveries", ["status", "lease_expires_at"])


def downgrade():
    # PostgreSQL refuses (transactionally) if new recurrence rows cannot fit the
    # old uniqueness rule. Never delete delivery history to force a downgrade.
    op.drop_constraint("uq_notification_deliveries_occurrence", "notification_deliveries", type_="unique")
    op.create_unique_constraint("uq_notification_deliveries_logical_identity", "notification_deliveries",
                                ["user_id", "alert_id", "channel", "notification_event"])
    op.drop_index("ix_notification_deliveries_lease", table_name="notification_deliveries")
    op.drop_column("notification_deliveries", "lease_expires_at")
    op.drop_column("notification_deliveries", "claim_token")
