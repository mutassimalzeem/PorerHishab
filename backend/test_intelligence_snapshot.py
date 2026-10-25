"""AI-13 tests: snapshot aggregation, isolation, scheduling and determinism.

The engine reads only the authenticated user's records, so a second user with
a large canary amount must never leak into the first user's intelligence.
Same database state + same as_of must produce equivalent intelligence.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (register ORM models)
from app.core.database import Base
from app.models.account import Account
from app.models.savings_goal import SavingsGoal
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.transactions import Transaction
from app.models.user import User
from app.services.intelligence.engine import build_financial_intelligence
from app.services.intelligence.snapshot import (
    build_snapshot,
    monthly_history,
)

AS_OF = date(2026, 10, 25)
CANARY_AMOUNT = Decimal("888888.00")


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed(db, user, rows=(), accounts=(), scheduled=(), goals=()):
    for day, amount, category, merchant in rows:
        db.add(Transaction(user_id=user.id, date=day, amount=Decimal(amount),
                           category=category, merchant=merchant))
    for currency in accounts:
        db.add(Account(user_id=user.id, name=f"{currency} account", currency=currency))
    for title, kind, amount, status, due in scheduled:
        db.add(ScheduledCashflowItem(user_id=user.id, title=title, kind=kind,
                                     amount=Decimal(amount), status=status, due_date=due))
    for name, target, saved, target_date in goals:
        db.add(SavingsGoal(user_id=user.id, name=name, target_amount=Decimal(target),
                           current_saved=Decimal(saved) if saved is not None else None,
                           target_date=target_date))
    db.commit()
    return user


def _new_user(db, key):
    user = User(email=f"{key}@example.com", hashed_password="x")
    db.add(user)
    db.commit()
    return user


def test_income_expense_and_net_are_observed_and_distinct(db):
    user = _new_user(db, "totals")
    _seed(db, user, rows=(
        (date(2026, 10, 5), "10000", "Salary", "Acme"),
        (date(2026, 10, 6), "-2500", "Food", "Dhaka Biryani House"),
        (date(2026, 10, 7), "-1200", "Transport", "Uber"),
    ))
    snapshot = build_snapshot(db, user.id, AS_OF)

    assert snapshot.income == Decimal("10000.00")
    assert snapshot.expenses == Decimal("3700.00")
    assert snapshot.net_cashflow == Decimal("6300.00")

    categories = {row["category"]: row for row in snapshot.category_spending}
    assert set(categories) == {"Food", "Transport"}
    assert categories["Food"]["expenses"] == Decimal("2500.00")
    assert categories["Food"]["transaction_count"] == 1


def test_empty_records_stay_none_not_zero(db):
    user = _new_user(db, "empty")
    snapshot = build_snapshot(db, user.id, AS_OF)
    assert snapshot.income is None
    assert snapshot.expenses is None
    assert snapshot.net_cashflow is None
    assert snapshot.category_spending == []
    assert snapshot.history.adequate is False


def test_monthly_history_marks_empty_months_unobserved_and_inadequate(db):
    user = _new_user(db, "sparse")
    _seed(db, user, rows=(
        # July missing entirely; August and September have records.
        (date(2026, 8, 10), "-4000", "Food", "Dhaka Biryani House"),
        (date(2026, 9, 10), "-4000", "Food", "Dhaka Biryani House"),
    ))
    history = monthly_history(db, user.id, AS_OF)
    assert history.months_with_records == ("2026-08", "2026-09")
    assert history.adequate is False
    assert history.monthly[0]["coverage"]["transaction_count"] == 0
    assert history.monthly[0]["income"] is None
    assert history.monthly[0]["expenses"] is None


def test_income_only_month_no_longer_crashes_the_baseline(db):
    # Regression: a history month with income but no expenses used to raise
    # TypeError when the baseline records were assembled.
    user = _new_user(db, "income_only")
    _seed(db, user, rows=(
        (date(2026, 7, 5), "5000", "Salary", "Acme"),
        (date(2026, 8, 5), "5000", "Salary", "Acme"),
        (date(2026, 8, 10), "-2000", "Food", "Dhaka Biryani House"),
        (date(2026, 9, 5), "5000", "Salary", "Acme"),
        (date(2026, 9, 10), "-2000", "Food", "Dhaka Biryani House"),
    ))
    history = monthly_history(db, user.id, AS_OF)
    assert history.adequate is True  # every history month has records
    assert history.baseline["average_monthly_expenses"] == Decimal("1333.33")
    assert history.baseline["average_monthly_income"] == Decimal("5000.00")


def test_scheduled_plans_are_separate_from_actuals(db):
    user = _new_user(db, "scheduled")
    _seed(db, user, rows=(
        (date(2026, 7, 10), "-1000", "Food", "Dhaka Biryani House"),
        (date(2026, 8, 10), "-1000", "Food", "Dhaka Biryani House"),
        (date(2026, 9, 10), "-1000", "Food", "Dhaka Biryani House"),
        (date(2026, 10, 10), "-1000", "Food", "Dhaka Biryani House"),
    ), scheduled=(
        ("Electricity bill", "expense", "6000.00", "scheduled", date(2026, 10, 28)),
        ("Settled bill", "expense", "9000.00", "paid", date(2026, 10, 27)),
        ("Withdrawn plan", "expense", "7000.00", "cancelled", date(2026, 10, 29)),
    ))
    intelligence = build_financial_intelligence(db, user.id, AS_OF)

    # Paid and cancelled plans are not obligations.
    obligations = intelligence.snapshot.scheduled_obligations
    assert obligations.expense_total == Decimal("6000.00")
    assert len(obligations.items) == 1
    assert obligations.items[0]["record_type"] == "plan"

    # Actuals only include recorded transactions, never plans.
    assert intelligence.cashflow.actual_expense == Decimal("4000.00")
    assert intelligence.snapshot.expenses == Decimal("1000.00")
    assert intelligence.cashflow.scheduled_income == Decimal("0.00")


def test_scheduled_income_never_becomes_actual_or_projected_money(db):
    user = _new_user(db, "scheduled_income")
    _seed(db, user, rows=(
        (date(2026, 7, 10), "-1000", "Food", "Dhaka Biryani House"),
        (date(2026, 8, 10), "-1000", "Food", "Dhaka Biryani House"),
        (date(2026, 9, 10), "-1000", "Food", "Dhaka Biryani House"),
    ), scheduled=(
        ("Expected bonus", "income", "50000.00", "scheduled", date(2026, 10, 30)),
    ))
    intelligence = build_financial_intelligence(db, user.id, AS_OF)
    cashflow = intelligence.cashflow

    assert cashflow.scheduled_income == Decimal("50000.00")
    assert cashflow.actual_income == Decimal("0.00")
    # The forecast estimate is purely from recorded history (income 0, planned
    # expenses 1000/month); the scheduled plan is never added into it.
    assert cashflow.forecast_income == Decimal("0.00")
    assert cashflow.forecast_net == Decimal("-1000.00")
    assert cashflow.forecast_income != cashflow.scheduled_income
    assert any("scheduled income" in line.lower()
               for line in cashflow.limitations)


def test_second_user_canary_never_leaks_into_another_users_intelligence(db):
    main = _new_user(db, "main")
    _seed(db, main, rows=(
        (date(2026, 10, 5), "10000", "Salary", "Acme"),
        (date(2026, 10, 6), "-500", "Food", "Dhaka Biryani House"),
    ))
    canary = _new_user(db, "canary")
    canary_marker_tx = "CANARY PRIVATE LEDGER"
    canary_marker_bill = "CANARY PRIVATE BILL"
    canary_marker_goal = "CANARY PRIVATE GOAL"
    _seed(db, canary, rows=(
        (date(2026, 10, 6), "-777777", "Food", canary_marker_tx),
        (date(2026, 7, 6), "-777777", "Food", canary_marker_tx),
        (date(2026, 8, 6), "-777777", "Food", canary_marker_tx),
        (date(2026, 9, 6), "-777777", "Food", canary_marker_tx),
    ), scheduled=(
        (canary_marker_bill, "expense", "888888.00", "scheduled", date(2026, 10, 27)),
    ), goals=(
        (canary_marker_goal, "100000", "50000", date(2026, 12, 31)),
    ))

    intelligence = build_financial_intelligence(db, main.id, AS_OF)
    text = repr(intelligence.to_dict())
    assert "777777" not in text
    assert "888888" not in text
    for marker in (canary_marker_tx, canary_marker_bill, canary_marker_goal):
        assert marker not in text


def test_same_state_and_as_of_produce_equivalent_intelligence(db):
    user = _new_user(db, "determinism")
    _seed(db, user, rows=(
        (date(2026, 7, 5), "30000", "Salary", "Acme"),
        (date(2026, 7, 10), "-4000", "Food", "Dhaka Biryani House"),
        (date(2026, 8, 5), "30000", "Salary", "Acme"),
        (date(2026, 8, 10), "-4000", "Food", "Dhaka Biryani House"),
        (date(2026, 9, 5), "30000", "Salary", "Acme"),
        (date(2026, 9, 10), "-4000", "Food", "Dhaka Biryani House"),
        (date(2026, 10, 5), "30000", "Salary", "Acme"),
        (date(2026, 10, 6), "-9000", "Food", "Dhaka Biryani House"),
    ), scheduled=(
        ("Electricity bill", "expense", "6000.00", "scheduled", date(2026, 10, 28)),
    ), goals=(
        ("Emergency fund", "60000", "30000", date(2026, 12, 31)),
    ))

    first = build_financial_intelligence(db, user.id, AS_OF).to_dict()
    second = build_financial_intelligence(db, user.id, AS_OF).to_dict()
    assert first == second


def test_snapshot_to_dict_is_frontend_friendly_and_private(db):
    user = _new_user(db, "dict")
    _seed(db, user, rows=(
        (date(2026, 10, 5), "10000", "Salary", "Acme"),
        (date(2026, 10, 6), "-500", "Food", "Dhaka Biryani House"),
    ))
    payload = build_snapshot(db, user.id, AS_OF).to_dict()
    assert "user_id" not in payload  # internal ids are not exposed
    assert payload["income"] == "10000.00"
    assert payload["value_kind"] == "observed"
    assert payload["data_coverage"]["period"]["is_complete"] is True
    assert payload["category_spending"][0]["category"] == "Food"


def test_non_bdt_account_records_are_excluded_from_facts(db):
    user = _new_user(db, "currency")
    _seed(db, user, rows=(
        (date(2026, 10, 5), "10000", "Salary", "Acme"),
    ))
    usd_account = Account(user_id=user.id, name="USD wallet", currency="USD")
    db.add(usd_account)
    db.commit()
    db.add(Transaction(user_id=user.id, account_id=usd_account.id,
                       date=date(2026, 10, 9), amount=Decimal("-99999.00"),
                       category="Shopping", merchant="Foreign Store"))
    db.commit()

    snapshot = build_snapshot(db, user.id, AS_OF)
    # The USD-account record is excluded entirely; the BDT salary remains.
    assert snapshot.income == Decimal("10000.00")
    assert snapshot.expenses == Decimal("0.00")  # no included expense rows
    assert snapshot.category_spending == []
