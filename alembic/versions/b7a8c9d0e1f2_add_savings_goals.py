"""Add user-reported savings goals.

Revision ID: b7a8c9d0e1f2
Revises: ec735533a563
"""
from alembic import op
import sqlalchemy as sa

revision = "b7a8c9d0e1f2"
down_revision = "ec735533a563"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "savings_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("current_saved", sa.Numeric(14, 2), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("target_amount > 0", name="ck_savings_goals_target"),
        sa.CheckConstraint("current_saved IS NULL OR current_saved >= 0", name="ck_savings_goals_saved"),
        sa.CheckConstraint("status IN ('active', 'completed', 'cancelled')", name="ck_savings_goals_status"),
        sa.CheckConstraint("status != 'completed' OR (current_saved IS NOT NULL AND current_saved >= target_amount)", name="ck_savings_goals_completed"),
    )
    op.create_index("ix_savings_goals_user_status", "savings_goals", ["user_id", "status"])


def downgrade():
    op.drop_index("ix_savings_goals_user_status", table_name="savings_goals")
    op.drop_table("savings_goals")
