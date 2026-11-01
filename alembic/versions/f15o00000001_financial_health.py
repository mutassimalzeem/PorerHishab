"""Financial health daily versioned snapshots."""
from alembic import op
import sqlalchemy as sa
revision = "f15o00000001"
down_revision = "f15n00000001"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("financial_health_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("overall_score", sa.Numeric(5, 2)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("coverage_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("data_quality_status", sa.String(16), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("calculation_version", sa.String(40), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "snapshot_date", "calculation_version", name="uq_health_user_date_version"),
        sa.CheckConstraint("overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)", name="ck_health_score"),
        sa.CheckConstraint("coverage_percent >= 0 AND coverage_percent <= 100", name="ck_health_coverage"))
    op.create_index("ix_financial_health_snapshots_user_id", "financial_health_snapshots", ["user_id"])

def downgrade():
    op.drop_table("financial_health_snapshots")
