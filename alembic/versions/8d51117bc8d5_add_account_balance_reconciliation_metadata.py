"""add account balance reconciliation metadata

Revision ID: 8d51117bc8d5
Revises: b7a8c9d0e1f2
Create Date: 2026-10-30 17:28:42.150297

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d51117bc8d5'
down_revision: Union[str, None] = 'b7a8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("balance_source", sa.String(length=30), nullable=True))
    op.add_column("accounts", sa.Column("balance_as_of", sa.DateTime(timezone=True), nullable=True))
    op.add_column("accounts", sa.Column("opening_balance", sa.Numeric(14, 2), nullable=True))
    op.add_column("accounts", sa.Column("opening_balance_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "opening_balance_date")
    op.drop_column("accounts", "opening_balance")
    op.drop_column("accounts", "balance_as_of")
    op.drop_column("accounts", "balance_source")
