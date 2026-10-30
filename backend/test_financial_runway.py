"""AI-15D accounting, uncertainty, date resolution and authenticated isolation."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models import Account, User, Transaction, ScheduledCashflowItem
from app.services.finance.account_reconciliation import reconcile_account_balance
from app.services.finance.obligation_reconciliation import confirm, reconcile, revoke
from app.services.finance.runway import financial_runway
from app.services.finance.coach import coach_purchase
from app.services.intelligence.engine import build_financial_intelligence
from app.services.intelligence.goals import goal_assessment
from app.models.savings_goal import SavingsGoal

D = Decimal
AS_OF = date(2026, 11, 1)


@pytest.fixture
def data():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        users = [User(email=f"runway-{n}@test.local", hashed_password="x") for n in range(2)]
        db.add_all(users)
        db.flush()
        account = Account(user_id=users[0].id, name="Cash", currency="BDT",
                          opening_balance=D("30000"), opening_balance_date=date(2026, 7, 1))
        db.add(account)
        db.commit()
        yield db, users, account
    engine.dispose()


def plan(db, user, amount="15000", kind="expense", due=AS_OF, status="scheduled"):
    item = ScheduledCashflowItem(user_id=user.id, title="Rent", kind=kind, amount=D(amount), due_date=due, status=status)
    db.add(item)
    db.commit()
    return item


def transaction(db, user, account=None, amount="-6000", day=AS_OF, **kw):
    row = Transaction(user_id=user.id, account_id=account.id if account else None, date=day, amount=D(amount), **kw)
    db.add(row)
    db.commit()
    return row


def history(db, user, income="2000", expense="1000"):
    for month in [8, 9, 10]:
        transaction(db, user, amount=income, day=date(2026, month, 2))
        transaction(db, user, amount="-" + expense, day=date(2026, month, 3))


def run(data, **kw):
    db, users, _ = data
    return financial_runway(db, users[0].id, as_of=AS_OF, **kw)


@pytest.mark.parametrize("source", ["reconciled", "derived", "reported", "unknown", "mismatch"])
def test_balance_selection(data, source):
    db, users, account = data
    if source in {"reported", "unknown"}:
        account.opening_balance = account.opening_balance_date = None
    if source in {"reported", "reconciled", "mismatch"}:
        account.current_balance = D("31000") if source == "mismatch" else D("30000")
    db.commit()
    result = run(data, mode="known_obligations")
    if source in {"unknown", "mismatch"}:
        assert result.starting_balance is result.projected_end_balance is None
        assert result.runway_status == "insufficient_data"
        assert result.confidence == "unknown"
    else:
        assert result.starting_balance == D("30000")
        assert result.balance_source == source
        assert result.projected_end_balance == D("30000")


def test_missing_account_does_not_become_zero_and_unknown_account_blocks_partial_sum(data):
    db, users, account = data
    assert financial_runway(db, users[1].id, as_of=AS_OF).starting_balance is None
    db.add(Account(user_id=users[0].id, name="Unknown", currency="BDT"))
    db.commit()
    assert run(data).starting_balance is None
    assert run(data).derived_balance is None


@pytest.mark.parametrize("kind,amounts,expected", [
    ("expense", [], "15000"), ("expense", ["6000"], "9000"),
    ("expense", ["15000"], "0"), ("expense", ["4000", "6000"], "5000"),
    ("expense", ["6000.25"], "8999.75"),
    ("income", ["6000"], "9000"), ("income", ["15000"], "0"),
])
def test_allocations_and_actuals_are_not_double_counted(data, kind, amounts, expected):
    db, users, account = data
    item = plan(db, users[0], kind=kind)
    for amount in amounts:
        row = transaction(db, users[0], account, amount=amount if kind == "income" else "-" + amount)
        confirm(db, users[0].id, item.id, row.id)
    result = run(data, mode="known_obligations")
    sign = D("1") if kind == "income" else D("-1")
    starting = D("30000") + sign * sum(map(D, amounts), D("0"))
    assert result.starting_balance == starting
    assert result.scheduled_expense_reserve == (D(expected) if kind == "expense" else 0)
    assert result.known_future_income == (D(expected) if kind == "income" else 0)
    assert result.projected_end_balance == starting - result.scheduled_expense_reserve
    assert item.amount == 15000
    assert db.query(Transaction).count() == len(amounts)
    if amounts:
        assert db.query(Transaction).all()[0].amount == sign * D(amounts[0])


def test_candidate_only_revocation_and_full_paid(data):
    db, users, account = data
    item = plan(db, users[0])
    row = transaction(db, users[0], account, amount="-15000")
    assert reconcile(db, users[0].id, item.id)["candidates"]
    assert run(data, mode="known_obligations").scheduled_expense_reserve == 15000
    confirm(db, users[0].id, item.id, row.id, full=True)
    assert run(data, mode="known_obligations").projected_end_balance == 15000
    revoke(db, users[0].id, item.id, row.id)
    result = run(data, mode="known_obligations")
    assert result.starting_balance == 15000
    assert result.scheduled_expense_reserve == 15000
    assert result.projected_end_balance == 0
    assert row.amount == -15000


@pytest.mark.parametrize("status", ["paid", "cancelled"])
def test_terminal_plans(data, status):
    db, users, _ = data
    plan(db, users[0], status=status)
    assert run(data, mode="known_obligations").scheduled_expense_reserve == 0


def test_inclusive_horizon_overdue_and_multiple_obligations(data):
    db, users, _ = data
    for due in [AS_OF - timedelta(days=1), AS_OF, AS_OF + timedelta(days=30), AS_OF + timedelta(days=31)]:
        plan(db, users[0], amount="100.25", due=due)
    result = run(data, mode="known_obligations")
    assert result.scheduled_expense_reserve == D("200.50")
    assert result.period.end == AS_OF + timedelta(days=30)


@pytest.mark.parametrize("amount,threshold,status,days", [
    ("20000", "0", "positive", None), ("30000", "0", "at_risk", None),
    ("29000", "1000", "at_risk", None), ("30000.01", "0", "cash_shortfall", 5),
])
def test_known_runway_and_first_shortfall(data, amount, threshold, status, days):
    db, users, _ = data
    plan(db, users[0], amount=amount, due=AS_OF + timedelta(days=5))
    result = run(data, mode="known_obligations", safety_threshold=D(threshold))
    assert result.runway_status == status
    assert result.runway_days == days
    assert result.first_shortfall_date == (AS_OF + timedelta(days=5) if days else None)
    assert result.minimum_projected_balance == D("30000") - D(amount)


def test_first_of_several_shortfalls_and_initial_negative(data):
    db, users, account = data
    plan(db, users[0], amount="20000", due=AS_OF + timedelta(days=1))
    plan(db, users[0], amount="20000", due=AS_OF + timedelta(days=3))
    plan(db, users[0], amount="20000", due=AS_OF + timedelta(days=5))
    assert run(data, mode="known_obligations").runway_days == 3
    account.opening_balance = D("-1")
    db.commit()
    assert run(data, mode="known_obligations").runway_days == 0


def test_historical_resolution_overlap_and_confidence(data):
    db, users, account = data
    account.current_balance = D("30000")
    db.commit()
    history(db, users[0])
    plan(db, users[0], amount="500")
    result = run(data, horizon_days=29)
    assert result.confidence == "high"
    assert result.forecast_income == D("2000")
    assert result.forecast_expense == D("1000")
    assert result.expected_expense_reserve == D("1000")
    assert result.projected_end_balance == D("31000")
    assert result.minimum_projected_balance == D("29000")
    assert result.runway_status == "positive"
    assert result.runway_days is result.first_shortfall_date is None
    assert run(data, horizon_days=29).model_dump() == result.model_dump()


def test_monthly_shortfall_does_not_invent_precise_day(data):
    db, users, account = data
    account.opening_balance = D("500")
    db.commit()
    history(db, users[0])
    result = run(data, horizon_days=29)
    assert result.runway_status == "cash_shortfall"
    assert result.minimum_projected_balance == -500
    assert result.projected_end_balance == 1500
    assert result.first_shortfall_period.start == AS_OF
    assert result.first_shortfall_period.end == date(2026, 11, 30)
    assert result.runway_days is result.first_shortfall_date is None


def test_missing_history_keeps_estimates_unknown(data):
    db, users, _ = data
    plan(db, users[0])
    result = run(data)
    assert result.starting_balance == 30000
    assert result.known_obligations_end_balance == 15000
    assert result.forecast_income is result.forecast_expense is result.projected_end_balance is None
    assert result.runway_status == "insufficient_data"
    assert not result.checkpoints


def test_other_users_and_currency_are_isolated(data):
    db, users, account = data
    before = run(data, mode="known_obligations").model_dump()
    foreign = Account(user_id=users[1].id, name="Foreign", opening_balance=D("999999"), opening_balance_date=AS_OF)
    usd = Account(user_id=users[0].id, name="USD", currency="USD", current_balance=D("999999"))
    db.add_all([foreign, usd]); db.commit()
    transaction(db, users[1], foreign, amount="-99999")
    transaction(db, users[0], usd, amount="99999")
    plan(db, users[1], amount="99999")
    assert run(data, mode="known_obligations").model_dump() == before
    assert run(data).forecast_income is None


def test_asof_filters_future_actuals_opening_and_report(data):
    db, users, account = data
    transaction(db, users[0], account, amount="-9999", day=AS_OF + timedelta(days=1))
    assert run(data, mode="known_obligations").starting_balance == 30000
    # Existing reconciliation callers retain their previous all-records behavior.
    assert reconcile_account_balance(db, account=account, user_id=users[0].id)["derived_balance"] == 20001
    account.opening_balance_date = AS_OF + timedelta(days=1)
    account.current_balance = D("9000")
    account.balance_as_of = datetime(2026, 11, 1, 20, tzinfo=timezone.utc)  # Nov 2 in Dhaka
    db.commit()
    assert run(data).starting_balance is None


def test_purchase_cannot_spend_unavailable_account_cash(data):
    db, users, account = data
    account.opening_balance = D("500")
    db.commit()
    request = SimpleNamespace(starting_balance=D("10000"), purchase_amount=D("1000"), safety_buffer=D("0"), horizon_days=30)
    result = coach_purchase(db, users[0].id, request, as_of=AS_OF)
    assert result["status"] == "not_recommended"
    assert result["remaining_after_purchase_and_reserve"] == -500
    assert result["runway"].starting_balance == 500


def test_purchase_checks_forecast_low_watermark_and_goals_are_capped(data):
    db, users, account = data
    account.opening_balance = D("2000")
    db.commit()
    history(db, users[0], income="100", expense="1000")
    request = SimpleNamespace(starting_balance=D("2000"), purchase_amount=D("1500"), safety_buffer=D("0"), horizon_days=29)
    assert coach_purchase(db, users[0].id, request, as_of=AS_OF)["status"] == "not_recommended"
    goal = SavingsGoal(user_id=users[0].id, name="Goal", target_amount=D("10000"), current_saved=D("0"), target_date=date(2026, 12, 1))
    db.add(goal); db.commit()
    assessment = goal_assessment(db, users[0].id, goal, AS_OF, {"adequate": True, "baseline": {"average_monthly_income": D("20000"), "average_monthly_expenses": D("1000")}})
    assert assessment.capacity == 2000


def test_intelligence_signal_consumes_runway(data):
    db, users, account = data
    history(db, users[0])
    result = build_financial_intelligence(db, users[0].id, AS_OF)
    signal = next(s for s in result.signals if s.signal_type == "cash_position")
    runway = run(data)
    assert signal.observed_value == runway.minimum_projected_balance
    assert signal.reference_value == runway.safety_threshold
    assert signal.estimate and signal.limitations


@pytest.mark.parametrize("kw", [{"horizon_days": 0}, {"horizon_days": 367}, {"safety_threshold": D("-1")}, {"safety_threshold": 1.5}, {"starting_balance": 1.5}, {"mode": "bad"}])
def test_invalid_service_inputs(data, kw):
    with pytest.raises(ValueError): run(data, **kw)


def test_api_auth_validation_decimal_serialization_and_unknowns(data):
    db, users, account = data
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            assert client.get("/finance/runway").status_code == 401
            app.dependency_overrides[get_current_user] = lambda: users[0]
            for query in ["horizon_days=0", "horizon_days=367", "safety_threshold=-1", "safety_threshold=1.001", "mode=bad", "as_of=bad"]:
                assert client.get("/finance/runway?" + query).status_code == 422
            response = client.get("/finance/runway", params={"as_of": AS_OF.isoformat(), "mode": "known_obligations"})
            assert response.status_code == 200
            body = response.json()
            assert body["starting_balance"] == "30000.00"
            assert body["first_shortfall_date"] is None
            assert body["period"]["start"] == AS_OF.isoformat()
            app.dependency_overrides[get_current_user] = lambda: users[1]
            body = client.get("/finance/runway").json()
            assert body["starting_balance"] is body["projected_end_balance"] is None
            assert body["runway_status"] == "insufficient_data"
    finally:
        app.dependency_overrides.clear()


def test_conflicting_report_and_transaction_snapshot_is_unknown(data):
    db, users, account = data
    account.opening_balance = account.opening_balance_date = None
    account.current_balance = D("30000")
    transaction(db, users[0], account, amount="-1", balance=D("100"))
    assert run(data).starting_balance is None
    assert run(data).reported_balance == 30000
    assert run(data).derived_balance == 100


def test_snapshot_and_mixed_account_sources(data):
    db, users, account = data
    account.opening_balance = account.opening_balance_date = None
    transaction(db, users[0], account, amount="100", balance=D("500.25"))
    db.add(Account(user_id=users[0].id, name="Reported", current_balance=D("100.10")))
    db.commit()
    result = run(data, mode="known_obligations")
    assert result.starting_balance == D("600.35")
    assert result.balance_source == "mixed"
    assert result.confidence == "low"


def test_historical_proration_crosses_month_boundary_exactly(data):
    db, users, _ = data
    history(db, users[0], income="3000", expense="1500")
    result = financial_runway(db, users[0].id, as_of=date(2026, 11, 30), horizon_days=1)
    expected_income = D("100.00") + D("96.77")
    expected_expense = D("50.00") + D("48.39")
    assert result.forecast_income == expected_income
    assert result.forecast_expense == expected_expense
    assert result.projected_end_balance == D("30000") + expected_income - expected_expense
    assert len(result.checkpoints) == 2
