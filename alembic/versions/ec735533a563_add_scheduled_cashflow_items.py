
"""add scheduled cashflow items

Revision ID: ec735533a563
Revises: 491b66ce6e6b
Create Date: 2026-10-25 11:59:28.579961

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ec735533a563"
down_revision: Union[str, None] = "491b66ce6e6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_cashflow_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('income', 'expense')",
            name="ck_scheduled_cashflow_items_kind",
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'paid', 'cancelled')",
            name="ck_scheduled_cashflow_items_status",
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_scheduled_cashflow_items_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_scheduled_cashflow_user_due_date",
        "scheduled_cashflow_items",
        ["user_id", "due_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduled_cashflow_user_due_date",
        table_name="scheduled_cashflow_items",
    )
    op.drop_table("scheduled_cashflow_items")
