"""AI-15S financial coach conversation and message persistence tables.

Revision ID: f15s00000001
Revises: f15r00000001
Create Date: 2026-11-02 12:35:00
"""

from alembic import op
import sqlalchemy as sa

revision = "f15s00000001"
down_revision = "f15r00000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coach_conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_coach_conversations_user_updated",
        "coach_conversations",
        ["user_id", "updated_at"],
    )

    op.create_table(
        "coach_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.String(64),
            sa.ForeignKey("coach_conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(50), nullable=True),
        sa.Column("claims_json", sa.JSON(), nullable=True),
        sa.Column("actions_json", sa.JSON(), nullable=True),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_coach_messages_conversation_created",
        "coach_messages",
        ["conversation_id", "created_at"],
    )


def downgrade():
    op.drop_index("ix_coach_messages_conversation_created", table_name="coach_messages")
    op.drop_table("coach_messages")
    op.drop_index("ix_coach_conversations_user_updated", table_name="coach_conversations")
    op.drop_table("coach_conversations")
