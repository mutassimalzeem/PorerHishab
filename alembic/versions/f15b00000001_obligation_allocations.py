"""Persist confirmed obligation allocations and revocations."""
from alembic import op
import sqlalchemy as sa
revision = "f15b00000001"
down_revision = "8d51117bc8d5"
branch_labels = None
depends_on = None

def upgrade():
    op.create_unique_constraint("uq_scheduled_cashflow_item_id_user", "scheduled_cashflow_items", ["id", "user_id"])
    op.create_unique_constraint("uq_transactions_id_user", "transactions", ["id", "user_id"])
    op.create_table("obligation_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["item_id", "user_id"], ["scheduled_cashflow_items.id", "scheduled_cashflow_items.user_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id", "user_id"], ["transactions.id", "transactions.user_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("amount > 0", name="ck_obligation_allocation_positive"))
    op.create_index("ix_obligation_allocation_user_item", "obligation_allocations", ["user_id", "item_id"])
    op.create_index("uq_obligation_active_transaction", "obligation_allocations", ["transaction_id"], unique=True, postgresql_where=sa.text("active"))

def downgrade():
    op.drop_table("obligation_allocations")
    op.drop_constraint("uq_transactions_id_user", "transactions", type_="unique")
    op.drop_constraint("uq_scheduled_cashflow_item_id_user", "scheduled_cashflow_items", type_="unique")
