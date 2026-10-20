"""rename transactions.dates to date

Revision ID: c2d11a3f4b5c
Revises: b348fd279e16
Create Date: 2026-10-20

Aligns the DB with Transaction.date (model renamed dates -> date).
Safe on fresh DBs (alembic upgrade head runs baseline then this).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2d11a3f4b5c'
down_revision: Union[str, None] = 'b348fd279e16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f('ix_transactions_dates'), table_name='transactions')
    op.alter_column('transactions', 'dates', new_column_name='date',
                    existing_type=sa.Date(), nullable=False)
    op.create_index(op.f('ix_transactions_date'), 'transactions', ['date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_transactions_date'), table_name='transactions')
    op.alter_column('transactions', 'date', new_column_name='dates',
                    existing_type=sa.Date(), nullable=False)
    op.create_index(op.f('ix_transactions_dates'), 'transactions', ['dates'], unique=False)
