"""Durable owner-scoped coach request recovery; legacy messages remain valid."""
from alembic import op
import sqlalchemy as sa

revision = "f17f00000001"
down_revision = "f15s00000002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("coach_messages", sa.Column("request_id", sa.String(36), nullable=True))
    op.create_unique_constraint("uq_coach_message_request_role", "coach_messages", ["user_id", "request_id", "role"])
    op.create_table(
        "coach_turns",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(64), sa.ForeignKey("coach_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("schedules_confirmed", sa.Boolean, nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("lease_token", sa.String(36), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "request_id", name="uq_coach_turn_owner_request"),
        sa.CheckConstraint("state IN ('processing', 'failed', 'completed')", name="ck_coach_turn_state"),
    )
    op.create_index("ix_coach_turn_conversation", "coach_turns", ["conversation_id", "id"])
    op.create_index("uq_coach_turn_processing", "coach_turns", ["conversation_id"], unique=True,
                    postgresql_where=sa.text("state = 'processing'"))


def downgrade():
    op.drop_table("coach_turns")
    op.drop_constraint("uq_coach_message_request_role", "coach_messages", type_="unique")
    op.drop_column("coach_messages", "request_id")
