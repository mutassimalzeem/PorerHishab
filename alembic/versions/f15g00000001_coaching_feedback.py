"""Persist current owner-scoped coaching feedback."""
from alembic import op
import sqlalchemy as sa
revision = "f15g00000001"
down_revision = "f15b00000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("coaching_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recommendation_id", sa.String(300), nullable=False),
        sa.Column("evidence_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snoozed_until", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "recommendation_id", name="uq_coaching_feedback_user_recommendation"),
        sa.CheckConstraint("status IN ('dismissed', 'acted_on', 'not_relevant', 'snoozed')", name="ck_coaching_feedback_status"),
        sa.CheckConstraint("(status = 'snoozed' AND snoozed_until IS NOT NULL) OR (status <> 'snoozed' AND snoozed_until IS NULL)", name="ck_coaching_feedback_snooze"))
    op.create_index("ix_coaching_feedback_user_id", "coaching_feedback", ["user_id"])
    op.create_index("ix_coaching_feedback_user_status", "coaching_feedback", ["user_id", "status"])


def downgrade():
    op.drop_table("coaching_feedback")
