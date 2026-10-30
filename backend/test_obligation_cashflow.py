"""AI-15C: persisted confirmations drive reserves, never candidate matches."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
import app.models  # noqa: F401
from app.models import User, ScheduledCashflowItem, Transaction
from app.schemas.intelligence import ObligationObservation
from app.services.finance.obligations import remaining_obligation, obligation_amounts
from app.services.finance.obligation_reconciliation import confirm, reconcile, revoke
from app.services.finance.coach import coach_cashflow, coach_purchase
from app.services.intelligence.facts import scheduled_totals, totals
from app.services.intelligence.signals import upcoming_expense_signals
from app.services.intelligence.snapshot import scheduled_obligations

DUE = date(2026, 11, 1)
ZERO = Decimal("0.00")


@pytest.fixture
def data():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        users = [User(email=f"{n}@test.local", hashed_password="x") for n in range(2)]
        db.add_all(users)
        db.flush()
        item = ScheduledCashflowItem(user_id=users[0].id, title="Rent", kind="expense",
                                     amount=Decimal("15000.00"), due_date=DUE)
        db.add(item)
        db.commit()
        yield db, users, item
    engine.dispose()


def tx(db, user, amount):
    row = Transaction(user_id=user.id, date=DUE - timedelta(days=1), amount=Decimal(amount))
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize("kind,amounts,expected", [
    ("expense", [], "15000.00"),
    ("expense", ["6000"], "9000.00"),
    ("expense", ["15000"], "0.00"),
    ("expense", ["4000", "6000"], "5000.00"),
    ("expense", ["6000.25"], "8999.75"),
    ("income", ["6000.25"], "8999.75"),
    ("income", ["15000"], "0.00"),
])
def test_remaining_and_forecast_reserve(data, kind, amounts, expected):
    db, users, item = data
    item.kind = kind
    db.commit()
    for value in amounts:
        row = tx(db, users[0], value if kind == "income" else "-" + value)
        confirm(db, users[0].id, item.id, row.id)
    value = remaining_obligation(db, users[0].id, item.id)
    assert value.original_amount == item.amount == Decimal("15000.00")
    assert value.remaining_amount == value.reserved_amount == Decimal(expected)
    expense, income = scheduled_totals(db, users[0].id, DUE, DUE)
    assert (expense, income) == ((Decimal(expected), ZERO) if kind == "expense" else (ZERO, Decimal(expected)))
    scenario = coach_cashflow(db, users[0].id, SimpleNamespace(starting_balance=Decimal("20000"), months_ahead=1), as_of=DUE)
    month = scenario["months"][0]
    assert month["scheduled_expenses"] == expense
    assert month["uncertain_scheduled_income"] == income
    assert month["balance_without_future_income"] == Decimal("20000") - expense
    assert bool(upcoming_expense_signals(db, users[0].id, DUE)) == (kind == "expense" and Decimal(expected) > 0)


def test_candidates_revocation_manual_paid_and_actuals(data):
    db, users, item = data
    row = tx(db, users[0], "-15000")
    assert reconcile(db, users[0].id, item.id)["candidates"]
    assert remaining_obligation(db, users[0].id, item.id).reserved_amount == 15000
    confirm(db, users[0].id, item.id, row.id, full=True)
    assert not scheduled_obligations(db, users[0].id, DUE).items
    assert remaining_obligation(db, users[0].id, item.id).reserved_amount == 0
    assert totals(db, users[0].id, row.date, DUE)["expenses"] == 15000
    revoke(db, users[0].id, item.id, row.id)
    assert scheduled_totals(db, users[0].id, DUE, DUE)[0] == 15000
    assert row.amount == Decimal("-15000")
    item.status = "paid"
    db.commit()
    assert remaining_obligation(db, users[0].id, item.id).reserved_amount == 0
    assert scheduled_totals(db, users[0].id, DUE, DUE) == (ZERO, ZERO)


def test_user_scope_windows_and_cancelled(data):
    db, users, item = data
    row = tx(db, users[0], "-6000")
    confirm(db, users[0].id, item.id, row.id)
    foreign = ScheduledCashflowItem(user_id=users[1].id, title="Other", kind="expense",
                                   amount=Decimal("15000"), due_date=DUE)
    db.add(foreign)
    db.commit()
    assert scheduled_totals(db, users[1].id, DUE, DUE)[0] == 15000
    with pytest.raises(HTTPException) as error:
        remaining_obligation(db, users[1].id, item.id)
    assert error.value.status_code == 404
    for start, end in [(DUE - timedelta(days=1), DUE - timedelta(days=1)),
                       (DUE + timedelta(days=1), DUE + timedelta(days=30))]:
        assert scheduled_totals(db, users[0].id, start, end) == (ZERO, ZERO)
    item.status = "cancelled"
    db.commit()
    assert scheduled_totals(db, users[0].id, DUE, DUE) == (ZERO, ZERO)


def test_snapshot_signal_and_purchase_share_remaining(data):
    db, users, item = data
    row = tx(db, users[0], "-6000.25")
    confirm(db, users[0].id, item.id, row.id)
    snapshot = scheduled_obligations(db, users[0].id, DUE).to_dict()
    parsed = ObligationObservation.model_validate(snapshot)
    observed = parsed.items[0]
    assert observed.original_amount == 15000
    assert observed.allocated_amount == Decimal("6000.25")
    assert observed.amount == observed.remaining_amount == Decimal("8999.75")
    signal = upcoming_expense_signals(db, users[0].id, DUE)[0]
    assert signal.observed_value == Decimal("8999.75")
    assert signal.evidence["original_amount"] == 15000
    request = SimpleNamespace(starting_balance=Decimal("20000"), purchase_amount=Decimal("1000"), safety_buffer=ZERO, horizon_days=30)
    purchase = coach_purchase(db, users[0].id, request, as_of=DUE)
    assert purchase["scheduled_expense_reserve"] == Decimal("8999.75")
    assert purchase["remaining_after_purchase_and_reserve"] == Decimal("10000.25")


def test_defensive_clamp():
    item = SimpleNamespace(amount=Decimal("15000.00"), status="scheduled")
    assert obligation_amounts(item, Decimal("15000.01")).remaining_amount == ZERO
