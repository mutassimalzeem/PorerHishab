"""AI-15S-K financial coach message structured fields persistence.

Revision ID: f15s00000002
Revises: f15s00000001
Create Date: 2026-11-02 17:30:00
"""

from alembic import op
import sqlalchemy as sa

revision = "f15s00000002"
down_revision = "f15s00000001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("coach_messages") as batch_op:
        batch_op.add_column(sa.Column("summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("evidence_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("warnings_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("limitations_json", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("coach_messages") as batch_op:
        batch_op.drop_column("limitations_json")
        batch_op.drop_column("warnings_json")
        batch_op.drop_column("evidence_json")
        batch_op.drop_column("summary")
