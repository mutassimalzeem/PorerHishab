"""add categorization columns to transactions

Revision ID: a7f3d91c2e05
Revises: c2d11a3f4b5c
Create Date: 2026-10-23

Adds the columns introduced for auto-categorization metadata:
category_confidence, category_method, category_reason.

Safe on fresh DBs: the baseline already creates 'subcategory'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7f3d91c2e05'
down_revision: Union[str, None] = 'c2d11a3f4b5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column(
        'category_confidence', sa.Numeric(4, 3), nullable=True))
    op.add_column('transactions', sa.Column(
        'category_method', sa.String(length=20), nullable=True))
    op.add_column('transactions', sa.Column(
        'category_reason', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('transactions', 'category_reason')
    op.drop_column('transactions', 'category_method')
    op.drop_column('transactions', 'category_confidence')
