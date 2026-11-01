"""AI-15Q isolated scenarios and immutable runs."""
from alembic import op
import sqlalchemy as sa
revision="f15q00000001"
down_revision="f15p00000001"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("financial_scenarios",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("name",sa.String(120),nullable=False),sa.Column("description",sa.String(1000),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("base_snapshot_reference",sa.String(64)),
        sa.Column("status",sa.String(16),nullable=False),sa.Column("calculation_version",sa.String(32),nullable=False),sa.Column("revision",sa.Integer(),nullable=False),
        sa.CheckConstraint("status IN ('draft','saved','archived')",name="ck_scenario_status"))
    op.create_index("ix_financial_scenarios_user_id","financial_scenarios",["user_id"])
    op.create_table("scenario_changes",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("scenario_id",sa.Integer(),sa.ForeignKey("financial_scenarios.id",ondelete="CASCADE"),nullable=False),
        sa.Column("change_type",sa.String(40),nullable=False),sa.Column("amount",sa.Numeric(14,2)),sa.Column("currency",sa.String(3),nullable=False),sa.Column("percentage",sa.Numeric(7,2)),
        sa.Column("effective_date",sa.Date(),nullable=False),sa.Column("end_date",sa.Date()),sa.Column("frequency",sa.String(12)),
        sa.Column("target_id",sa.Integer()),sa.Column("target_date",sa.Date()),sa.Column("description",sa.String(500),nullable=False))
    op.create_index("ix_scenario_changes_scenario_id","scenario_changes",["scenario_id"])
    op.create_table("scenario_runs",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("scenario_id",sa.Integer(),sa.ForeignKey("financial_scenarios.id",ondelete="CASCADE"),nullable=False),
        sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("idempotency_key",sa.String(80),nullable=False),sa.Column("request",sa.JSON(),nullable=False),
        sa.Column("calculation_version",sa.String(32),nullable=False),sa.Column("baseline_snapshot_date",sa.Date(),nullable=False),
        sa.Column("baseline_snapshot_reference",sa.String(64),nullable=False),sa.Column("evidence",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("user_id","idempotency_key",name="uq_scenario_run_request"))
    op.create_index("ix_scenario_runs_scenario_id","scenario_runs",["scenario_id"])
    op.create_table("scenario_comparisons",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("run_id",sa.Integer(),sa.ForeignKey("scenario_runs.id",ondelete="CASCADE"),nullable=False),sa.Column("metric",sa.String(80),nullable=False),
        *[sa.Column(n,sa.Numeric(18,2)) for n in ("baseline_value","scenario_value","absolute_delta")],sa.Column("percentage_delta",sa.Numeric(24,2)),
        sa.Column("percentage_status",sa.String(24),nullable=False),sa.Column("direction",sa.String(16),nullable=False),sa.Column("status",sa.String(40),nullable=False),sa.Column("reason",sa.String(500)),
        sa.UniqueConstraint("run_id","metric",name="uq_scenario_run_metric"))
    op.create_index("ix_scenario_comparisons_run_id","scenario_comparisons",["run_id"])

def downgrade():
    for table in ("scenario_comparisons","scenario_runs","scenario_changes","financial_scenarios"): op.drop_table(table)
