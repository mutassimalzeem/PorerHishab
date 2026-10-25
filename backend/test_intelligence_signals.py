"""AI-13 tests: deterministic signals, evidence and stable ids.

Signals must fire exactly on the product's thresholds, stay silent on
insufficient history, carry structured evidence from the user's own records,
label estimates as estimates, and produce stable deterministic ids.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (register ORM models)
from app.core.database import Base
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.savings_goal import SavingsGoal
from app.models.transactions import Transaction
from app.models.user import User
from app.services.intelligence.engine import build_financial_intelligence
from app.services.intelligence.signals import (
    INCREASE_FACTOR,
    REDUCTION_FRACTION,
    REDUCIBLE_CATEGORIES,
    UNUSUAL_FACTOR,
    build_signals,
    savings_opportunity_signals,
    upcoming_expense_signals,
)
from app.services.intelligence.snapshot import monthly_history
from types import SimpleNamespace

AS_OF = date(2026, 10, 25)


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


def _new_user(db, key):
    user = User(email=f"{key}@example.com", hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _add_transactions(db, user, entries):
    for day, amount, category, merchant in entries:
        db.add(Transaction(user_id=user.id, date=day, amount=Decimal(amount),
                           category=category, merchant=merchant))
    db.commit()


def _history(food_amounts):
    """July..September salary + Food spending with the given amounts."""
    entries = []
    for month, amount in zip((7, 8, 9), food_amounts):
        entries.append((date(2026, month, 5), "30000", "Salary", "Acme Corp Payroll"))
        entries.append(
            (date(2026, month, 10), f"-{amount}", "Food", "Dhaka Biryani House"))
    return entries


def _engine_signals(db, user, as_of=AS_OF):
    history = monthly_history(db, user.id, as_of)
    return build_signals(
        db, user.id, as_of,
        SimpleNamespace(adequate=history.adequate,
                        baseline=history.baseline,
                        monthly=history.monthly))


def _by_type(signals):
    grouped: dict[str, list] = {}
    for signal in signals:
        grouped.setdefault(signal.signal_type, []).append(signal)
    return grouped


# -- unusual spending -----------------------------------------------------------


def test_unusual_spending_fires_above_half_against_the_prior_ceiling(db):
    user = _new_user(db, "unusual_true")
    _add_transactions(db, user, _history(("4000", "4000", "4000")) + [
        (date(2026, 10, 5), "30000", "Salary", "Acme Corp Payroll"),
        (date(2026, 10, 6), "-9000", "Food", "Dhaka Biryani House"),
    ])
    signals = _by_type(_engine_signals(db, user))
    unusual = signals["unusual_spending"]
    assert len(unusual) == 1
    assert unusual[0].evidence["current_expenses"] == Decimal("9000.00")
    assert unusual[0].evidence["largest_prior_month"] == Decimal("4000.00")
    assert unusual[0].observed_period.start == date(2026, 10, 1)
    assert unusual[0].observed_period.end == AS_OF
    assert unusual[0].observed_period.is_complete is False
    assert unusual[0].estimate is False
    assert unusual[0].stable_id == "unusual-spending:2026-10"


def test_unusual_spending_stays_silent_at_the_boundary(db):
    user = _new_user(db, "unusual_false")
    _add_transactions(db, user, _history(("4000", "4000", "4000")) + [
        (date(2026, 10, 5), "30000", "Salary", "Acme Corp Payroll"),
        (date(2026, 10, 6), "-6000", "Food", "Dhaka Biryani House"),
    ])
    assert "unusual_spending" not in _by_type(_engine_signals(db, user))


# -- savings opportunity (category increase) --------------------------------------


def test_savings_opportunity_fires_on_a_reducible_category_increase(db):
    user = _new_user(db, "savings_true")
    _add_transactions(db, user, _history(("4000", "5000", "9000")))
    signals = savings_opportunity_signals(
        __import__("sqlalchemy.orm", fromlist=["Session"]).Session and db,
        user.id, AS_OF, history_adequate=True,
        comparison_basis={"Food": Decimal("5000.00")})
    assert len(signals) == 1
    signal = signals[0]
    assert signal.subject == "Food"
    assert signal.evidence["latest_expenses"] == Decimal("9000.00")
    assert signal.evidence["previous_expenses"] == Decimal("5000.00")
    assert signal.evidence["estimated_monthly_saving"] == Decimal("900.00")
    assert signal.evidence["period_start"] == date(2026, 9, 1)
    assert signal.evidence["period_end"] == date(2026, 9, 30)
    assert signal.observed_value == Decimal("9000.00")
    assert signal.delta == Decimal("4000.00")
    assert signal.percentage_change == Decimal("80.00")
    assert signal.estimate is True
    assert signal.estimate_label == "estimate"
    assert signal.stable_id.startswith("review-category:2026-09:")


def test_savings_opportunity_stays_silent_at_the_increase_boundary(db):
    user = _new_user(db, "savings_false")
    _add_transactions(db, user, _history(("4000", "5000", "5000")))
    signals = savings_opportunity_signals(
        db, user.id, AS_OF, history_adequate=True,
        comparison_basis={"Food": Decimal("5000.00")})
    assert signals == []


def test_non_reducible_categories_never_become_opportunities(db):
    user = _new_user(db, "housing")
    _add_transactions(db, user, (
        (date(2026, 7, 5), "30000", "Salary", "Acme Corp Payroll"),
        (date(2026, 7, 10), "-4000", "Housing", "Landlord"),
        (date(2026, 8, 5), "30000", "Salary", "Acme Corp Payroll"),
        (date(2026, 8, 10), "-5000", "Housing", "Landlord"),
        (date(2026, 9, 5), "30000", "Salary", "Acme Corp Payroll"),
        (date(2026, 9, 10), "-12000", "Housing", "Landlord"),
    ))
    history = monthly_history(db, user.id, AS_OF)
    signals = savings_opportunity_signals(
        db, user.id, AS_OF, history_adequate=history.adequate,
        comparison_basis={"Housing": Decimal("5000.00")})
    assert signals == []


def test_product_thresholds_match_the_coach_contract():
    assert INCREASE_FACTOR == Decimal("1.10")
    assert REDUCTION_FRACTION == Decimal("0.10")
    assert UNUSUAL_FACTOR == Decimal("1.5")
    assert REDUCIBLE_CATEGORIES == frozenset(
        {"Food", "Shopping", "Entertainment", "Subscription", "Travel"})


def test_insufficient_history_gates_history_signals(db):
    user = _new_user(db, "insufficient")
    # July is empty: only two complete history months exist.
    _add_transactions(db, user, (
        (date(2026, 8, 5), "30000", "Salary", "Acme Corp Payroll"),
        (date(2026, 8, 10), "-4000", "Food", "Dhaka Biryani House"),
        (date(2026, 9, 5), "30000", "Salary", "Acme Corp Payroll"),
        (date(2026, 9, 10), "-9000", "Food", "Dhaka Biryani House"),
        (date(2026, 10, 5), "30000", "Salary", "Acme Corp Payroll"),
        (date(2026, 10, 6), "-9000", "Food", "Dhaka Biryani House"),
    ))
    grouped = _by_type(_engine_signals(db, user))
    assert "savings_opportunity" not in grouped
    assert "unusual_spending" not in grouped
    assert "projected_shortfall" not in grouped
    # Deterministic plan facts do not depend on history depth.
    assert "upcoming_expense" not in grouped  # no plans were seeded


# -- upcoming scheduled obligation --------------------------------------------------


def test_upcoming_expense_lists_only_scheduled_plans(db):
    user = _new_user(db, "upcoming")
    db.add_all([
        ScheduledCashflowItem(user_id=user.id, title="Electricity bill",
                              kind="expense", amount=Decimal("6000.00"),
                              status="scheduled",
                              due_date=AS_OF + timedelta(days=3)),
        ScheduledCashflowItem(user_id=user.id, title="Old rent",
                              kind="expense", amount=Decimal("9000.00"),
                              status="paid", due_date=AS_OF + timedelta(days=1)),
        ScheduledCashflowItem(user_id=user.id, title="Future rent",
                              kind="expense", amount=Decimal("9000.00"),
                              status="scheduled",
                              due_date=AS_OF + timedelta(days=40)),
        ScheduledCashflowItem(user_id=user.id, title="Bonus expectation",
                              kind="income", amount=Decimal("20000.00"),
                              status="scheduled", due_date=AS_OF + timedelta(days=5)),
    ])
    db.commit()
    signals = upcoming_expense_signals(db, user.id, AS_OF)
    assert len(signals) == 1
    signal = signals[0]
    assert signal.evidence["title"] == "Electricity bill"
    assert signal.evidence["amount"] == Decimal("6000.00")
    assert signal.evidence["record_type"] == "plan"
    assert signal.observed_period.start == AS_OF
    assert signal.observed_period.end == AS_OF + timedelta(days=3)
    assert signal.stable_id == (
        f"scheduled-expense:{signal.evidence['scheduled_item_id']}:"
        f"{AS_OF + timedelta(days=3)}")


# -- projected shortfall --------------------------------------------------------------


def test_projected_shortfall_fires_only_on_a_negative_average_net(db):
    user_true = _new_user(db, "shortfall_true")
    _add_transactions(db, user_true, _history(("35000", "35000", "35000")))
    grouped = _by_type(_engine_signals(db, user_true))
    shortfall = grouped["projected_shortfall"]
    assert len(shortfall) == 1
    assert shortfall[0].evidence["estimated_monthly_net"] == Decimal("-5000.00")
    assert shortfall[0].evidence["is_estimate"] is True
    assert shortfall[0].estimate is True
    assert shortfall[0].stable_id == "estimated-deficit:2026-10"

    user_false = _new_user(db, "shortfall_false")
    _add_transactions(db, user_false, _history(("15000", "15000", "15000")))
    assert "projected_shortfall" not in _by_type(_engine_signals(db, user_false))


# -- goal progress ----------------------------------------------------------------------


def test_goal_progress_reports_each_active_goal(db):
    user = _new_user(db, "goal")
    _add_transactions(db, user, _history(("5000", "5000", "5000")))
    db.add(SavingsGoal(user_id=user.id, name="Emergency fund",
                       target_amount=Decimal("60000"),
                       current_saved=Decimal("30000"),
                       target_date=date(2026, 12, 31), status="active"))
    db.commit()
    grouped = _by_type(_engine_signals(db, user))
    goals = grouped["goal_progress"]
    assert len(goals) == 1
    evidence = goals[0].evidence
    assert evidence["name"] == "Emergency fund"
    assert evidence["saved_source"] == "user_reported"
    assert evidence["current_saved"] == Decimal("30000.00")
    assert evidence["affordability"] == "appears_feasible"
    assert goals[0].observed_period.start == AS_OF
    assert goals[0].observed_period.end == date(2026, 12, 31)
    assert goals[0].stable_id == (
        f"goal-progress:{evidence['goal_id']}:2026-10")

    cancelled = _new_user(db, "cancelled")
    _add_transactions(db, cancelled, _history(("5000", "5000", "5000")))
    db.add(SavingsGoal(user_id=cancelled.id, name="Old goal",
                       target_amount=Decimal("60000"),
                       current_saved=Decimal("60000"),
                       target_date=date(2026, 12, 31), status="cancelled"))
    db.commit()
    grouped = _by_type(_engine_signals(db, cancelled))
    # Only active goals produce progress signals (completed/cancelled rows
    # are facts, not ongoing work).
    assert "goal_progress" not in grouped


def test_goal_with_unknown_savings_states_the_limitation(db):
    user = _new_user(db, "goal_null")
    _add_transactions(db, user, _history(("5000", "5000", "5000")))
    db.add(SavingsGoal(user_id=user.id, name="Vague goal",
                       target_amount=Decimal("60000"),
                       current_saved=None,
                       target_date=date(2026, 12, 31), status="active"))
    db.commit()
    grouped = _by_type(_engine_signals(db, user))
    signal = grouped["goal_progress"][0]
    assert signal.evidence["affordability"] == "unknown"
    assert any("unknown" in line for line in signal.limitations)


def test_no_signals_without_any_records(db):
    user = _new_user(db, "empty")
    assert _engine_signals(db, user) == []


def test_signal_ids_and_evidence_are_deterministic(db):
    user_a = _new_user(db, "det_a")
    user_b = _new_user(db, "det_b")
    seeded_transactions = _history(("4000", "5000", "9000"))
    _add_transactions(db, user_a, seeded_transactions)
    _add_transactions(db, user_b, seeded_transactions)

    signals_a = savings_opportunity_signals(
        db, user_a.id, AS_OF, history_adequate=True,
        comparison_basis={"Food": Decimal("5000.00")})
    signals_b = savings_opportunity_signals(
        db, user_b.id, AS_OF, history_adequate=True,
        comparison_basis={"Food": Decimal("5000.00")})
    # Identical shape and money evidence, and deliberately identical ids:
    # the id encodes stable properties (type+month+category), no user data.
    assert [s.stable_id for s in signals_a] == [s.stable_id for s in signals_b]
    assert [s.evidence for s in signals_a] == [s.evidence for s in signals_b]


def test_full_engine_intelligence_is_deterministic_and_exposes_estimates(db):
    user = _new_user(db, "engine")
    _add_transactions(db, user, _history(("4000", "5000", "9000")))

    first = build_financial_intelligence(db, user.id, AS_OF).to_dict()
    second = build_financial_intelligence(db, user.id, AS_OF).to_dict()
    assert first == second

    # The engine distinguishes observed from estimated at the contract level.
    assert first["snapshot"]["value_kind"] == "observed"
    assert first["cashflow"]["type"] == "forecast"
    assert first["cashflow"]["estimated"] is True
    savings = [s for s in first["signals"]
               if s["signal_type"] == "savings_opportunity"]
    assert savings and savings[0]["estimate"] is True
    assert "user_id" not in first["snapshot"]


