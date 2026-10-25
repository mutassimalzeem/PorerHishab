
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint

from app.core.database import Base
from app.models.scheduled_cashflow_item import ScheduledCashflowItem


def test_scheduled_cashflow_table_is_registered():
    table = Base.metadata.tables["scheduled_cashflow_items"]

    assert table is ScheduledCashflowItem.__table__


def test_scheduled_cashflow_has_expected_columns():
    table = ScheduledCashflowItem.__table__

    expected_columns = {
        "id",
        "user_id",
        "title",
        "kind",
        "amount",
        "due_date",
        "status",
        "category",
        "notes",
        "created_at",
        "updated_at",
    }

    assert expected_columns.issubset(set(table.columns.keys()))


def test_scheduled_cashflow_amount_uses_fixed_precision():
    column = ScheduledCashflowItem.__table__.columns["amount"]

    assert column.type.precision == 14
    assert column.type.scale == 2


def test_scheduled_cashflow_has_user_foreign_key_with_cascade():
    column = ScheduledCashflowItem.__table__.columns["user_id"]

    foreign_key = next(iter(column.foreign_keys))

    assert foreign_key.target_fullname == "users.id"
    assert foreign_key.ondelete == "CASCADE"


def test_scheduled_cashflow_amount_is_required_and_positive():
    table = ScheduledCashflowItem.__table__

    assert table.columns["amount"].nullable is False
    assert any(
        isinstance(constraint, CheckConstraint)
        and "amount > 0" in str(constraint.sqltext)
        for constraint in table.constraints
    )


def test_scheduled_cashflow_kind_and_status_are_constrained():
    table = ScheduledCashflowItem.__table__
    check_sql = " ".join(
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    )

    assert "income" in check_sql
    assert "expense" in check_sql
    assert "scheduled" in check_sql
    assert "paid" in check_sql
    assert "cancelled" in check_sql


def test_scheduled_cashflow_has_user_due_date_index():
    table = ScheduledCashflowItem.__table__

    index_columns = {
        tuple(column.name for column in index.columns)
        for index in table.indexes
    }

    assert ("user_id", "due_date") in index_columns


def test_amount_and_date_python_types():
    # Confirms the expected domain types used by the model.
    assert isinstance(Decimal("1250.50"), Decimal)
    assert isinstance(date(2026, 11, 1), date)
