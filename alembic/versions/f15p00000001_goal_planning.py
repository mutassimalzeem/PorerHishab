"""Extend existing savings goals; versioned plans, milestones and progress ledger."""
from alembic import op
import sqlalchemy as sa
revision = "f15p00000001"
down_revision = "f15o00000001"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("savings_goals") as b:
        b.alter_column("target_date", existing_type=sa.Date(), nullable=True)
        b.add_column(sa.Column("goal_type",sa.String(24),nullable=False,server_default="savings"))
        b.add_column(sa.Column("currency",sa.String(3),nullable=False,server_default="BDT"))
        b.add_column(sa.Column("priority",sa.Integer(),nullable=False,server_default="3"))
        b.drop_constraint("ck_savings_goals_status",type_="check")
        b.create_check_constraint("ck_savings_goals_status","status IN ('active','paused','completed','cancelled')")
        b.create_check_constraint("ck_goal_priority","priority BETWEEN 1 AND 5")
        b.create_check_constraint("ck_goal_currency","currency = 'BDT'")
        b.create_check_constraint("ck_goal_type","goal_type IN ('emergency_fund','purchase','savings','debt_repayment','expense_reduction','custom')")
    owner=lambda: [sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),sa.Column("goal_id",sa.Integer(),sa.ForeignKey("savings_goals.id",ondelete="CASCADE"),nullable=False)]
    op.create_table("goal_plans",sa.Column("id",sa.Integer(),primary_key=True),*owner(),sa.Column("version",sa.Integer(),nullable=False),sa.Column("fingerprint",sa.String(64),nullable=False),sa.Column("profile",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("user_id","goal_id","version",name="uq_goal_plan_version"))
    op.create_index("ix_goal_plan_owner_goal","goal_plans",["user_id","goal_id"])
    op.create_table("goal_milestones",sa.Column("id",sa.Integer(),primary_key=True),*owner(),sa.Column("plan_id",sa.Integer(),sa.ForeignKey("goal_plans.id",ondelete="CASCADE"),nullable=False),sa.Column("sequence",sa.Integer(),nullable=False),sa.Column("due_date",sa.Date(),nullable=False),sa.Column("target_cumulative",sa.Numeric(14,2),nullable=False),sa.Column("expected_contribution",sa.Numeric(14,2),nullable=False),sa.Column("status",sa.String(24),nullable=False),sa.Column("completed_at",sa.DateTime(timezone=True)),sa.UniqueConstraint("plan_id","sequence",name="uq_goal_milestone_sequence"),sa.CheckConstraint("target_cumulative > 0 AND expected_contribution > 0",name="ck_milestone_amount"),sa.CheckConstraint("status IN ('pending','missed','reported_completed')",name="ck_milestone_status"))
    op.create_index("ix_goal_milestone_owner_goal","goal_milestones",["user_id","goal_id"])
    op.create_table("goal_progress_events",sa.Column("id",sa.Integer(),primary_key=True),*owner(),sa.Column("idempotency_key",sa.String(120),nullable=False),sa.Column("kind",sa.String(32),nullable=False),sa.Column("payload",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("user_id","idempotency_key",name="uq_goal_event_request"))
    op.create_index("ix_goal_event_owner_goal","goal_progress_events",["user_id","goal_id"])

def downgrade():
    op.drop_table("goal_progress_events");op.drop_table("goal_milestones");op.drop_table("goal_plans")
    # Legacy schema requires a deadline and cannot represent paused goals.
    op.execute("UPDATE savings_goals SET target_date = CAST(created_at AS DATE) WHERE target_date IS NULL")
    op.execute("UPDATE savings_goals SET status = 'active' WHERE status = 'paused'")
    with op.batch_alter_table("savings_goals") as b:
        for name in ("ck_goal_type","ck_goal_currency","ck_goal_priority","ck_savings_goals_status"):b.drop_constraint(name,type_="check")
        b.create_check_constraint("ck_savings_goals_status","status IN ('active','completed','cancelled')")
        for name in ("priority","currency","goal_type"):b.drop_column(name)
        b.alter_column("target_date",existing_type=sa.Date(),nullable=False)
