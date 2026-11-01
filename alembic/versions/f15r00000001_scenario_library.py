"""AI-15R scenario lifecycle metadata; financial calculation tables are unchanged."""
from alembic import op
import sqlalchemy as sa
revision="f15r00000001"
down_revision="f15q00000001"
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table("financial_scenarios") as batch:
        batch.add_column(sa.Column("updated_at",sa.DateTime(timezone=True),nullable=True))
        batch.add_column(sa.Column("saved_at",sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("archived_at",sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("source_scenario_id",sa.Integer()))
        batch.create_foreign_key("fk_scenario_library_source","financial_scenarios",["source_scenario_id"],["id"],ondelete="SET NULL")
    op.execute("UPDATE financial_scenarios SET updated_at=created_at")
    with op.batch_alter_table("financial_scenarios") as batch:
        batch.alter_column("updated_at",existing_type=sa.DateTime(timezone=True),nullable=False)
    op.create_index("ix_scenario_library_owner_status_updated","financial_scenarios",["user_id","status","updated_at","id"])

def downgrade():
    op.drop_index("ix_scenario_library_owner_status_updated",table_name="financial_scenarios")
    with op.batch_alter_table("financial_scenarios") as batch:
        batch.drop_constraint("fk_scenario_library_source",type_="foreignkey")
        for name in ("source_scenario_id","archived_at","saved_at","updated_at"):batch.drop_column(name)
