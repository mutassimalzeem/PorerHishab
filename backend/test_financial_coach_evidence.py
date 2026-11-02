"""Unit tests for deterministic financial coach evidence assembly (AI-15S-C)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import Account, ScheduledCashflowItem, Transaction, User
from app.models.financial_alert import FinancialAlert
from app.models.savings_goal import SavingsGoal
from app.schemas.financial_coach import CoachIntent, EvidenceType
from app.services.finance.financial_coach_evidence import (
    EvidencePackage,
    FinancialCoachEvidenceAssembler,
    assemble_financial_evidence,
    parse_question_date_period,
)
from app.services.finance.financial_coach_router import IntentRoute, route_financial_coach_question

DAY = date(2026, 11, 1)
NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def users(db_session):
    u1 = User(email="user1@example.com", hashed_password="hashed_pw_1")
    u2 = User(email="user2@example.com", hashed_password="hashed_pw_2")
    db_session.add_all([u1, u2])
    db_session.commit()
    return u1, u2


def seed_user_finances(db: Session, user: User):
    # Add transactions across 3 months
    # August, September, October 2026
    for month in (8, 9, 10):
        # Income
        db.add(Transaction(user_id=user.id, date=date(2026, month, 5), amount=D("40000.00"), category="Salary"))
        # Expenses: Food, Rent, Utilities
        db.add(Transaction(user_id=user.id, date=date(2026, month, 10), amount=-D("12000.00"), category="Food"))
        db.add(Transaction(user_id=user.id, date=date(2026, month, 15), amount=-D("15000.00"), category="Rent"))
        db.add(Transaction(user_id=user.id, date=date(2026, month, 20), amount=-D("3000.00"), category="Utilities"))

    # Also add current month transaction (November 1, 2026)
    db.add(Transaction(user_id=user.id, date=DAY, amount=-D("1500.00"), category="Food"))

    # Reconciled Account
    acc = Account(
        user_id=user.id,
        name="Primary bKash",
        currency="BDT",
        opening_balance=D("50000.00"),
        opening_balance_date=date(2026, 8, 1),
        current_balance=D("50000.00"),
        balance_as_of=NOW,
    )
    db.add(acc)

    # Scheduled Bill
    bill = ScheduledCashflowItem(
        user_id=user.id,
        title="Internet Bill",
        kind="expense",
        amount=D("1200.00"),
        due_date=DAY + timedelta(days=10),
        status="scheduled",
    )
    db.add(bill)

    # Goal
    goal = SavingsGoal(
        user_id=user.id,
        name="Emergency Fund",
        target_amount=D("60000.00"),
        current_saved=D("30000.00"),
        target_date=date(2027, 3, 1),
        status="active",
        priority=1,
    )
    db.add(goal)

    db.commit()


def test_spending_analysis_evidence(db_session, users):
    u1, _ = users
    seed_user_finances(db_session, u1)

    question = "Where does my money go this month?"
    route = route_financial_coach_question(question)
    assert route.intent == CoachIntent.SPENDING_ANALYSIS

    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)

    assert pkg.intent == CoachIntent.SPENDING_ANALYSIS
    assert not pkg.requires_clarification
    assert pkg.period_start == date(2026, 11, 1)
    assert pkg.period_end == DAY

    # Check evidence items
    ev_ids = pkg.evidence_ids
    assert "ev_spending_total_expenses" in ev_ids
    assert "ev_spending_categories" in ev_ids
    assert "ev_spending_tx_count" in ev_ids

    total_exp_ev = pkg.get_evidence_by_id("ev_spending_total_expenses")
    assert total_exp_ev is not None
    assert total_exp_ev.evidence_type == EvidenceType.DERIVED_FACT
    assert total_exp_ev.value == D("1500.00")
    assert total_exp_ev.unit == "BDT"
    assert total_exp_ev.source == "intelligence_facts.totals"


def test_cross_user_isolation(db_session, users):
    u1, u2 = users
    seed_user_finances(db_session, u1)

    # u2 has only 1 transaction of 250 BDT
    db_session.add(Transaction(user_id=u2.id, date=DAY, amount=-D("250.00"), category="Snacks"))
    db_session.commit()

    question = "How much did I spend this month?"
    route = route_financial_coach_question(question)

    # Assemble for u2
    pkg_u2 = assemble_financial_evidence(db_session, u2.id, route, question, as_of=DAY)
    total_exp_ev = pkg_u2.get_evidence_by_id("ev_spending_total_expenses")
    assert total_exp_ev is not None
    # Must only reflect u2's 250 BDT, never u1's 1500 BDT
    assert total_exp_ev.value == D("250.00")

    # u2 has no goals
    goal_route = route_financial_coach_question("how is my savings goal")
    pkg_goals_u2 = assemble_financial_evidence(db_session, u2.id, goal_route, "how is my savings goal", as_of=DAY)
    assert "active_goals" in pkg_goals_u2.missing_data
    goal_count_ev = pkg_goals_u2.get_evidence_by_id("ev_goals_active_count")
    assert goal_count_ev is not None
    assert goal_count_ev.value == 0


def test_empty_financial_history(db_session, users):
    u1, _ = users
    # User has no transactions or accounts
    question = "How much have I spent this month?"
    route = route_financial_coach_question(question)
    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)

    assert "transactions_in_period" in pkg.missing_data
    tx_count_ev = pkg.get_evidence_by_id("ev_spending_tx_count")
    assert tx_count_ev is not None
    assert tx_count_ev.value == 0
    # No fake 0-value derived totals created when empty
    assert "ev_spending_total_expenses" not in pkg.evidence_ids


def test_cashflow_evidence_with_account_position(db_session, users):
    u1, _ = users
    seed_user_finances(db_session, u1)

    question = "What is my cashflow and future balance?"
    route = route_financial_coach_question(question)
    assert route.intent == CoachIntent.CASHFLOW

    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)
    assert not pkg.requires_clarification
    assert "ev_cashflow_starting_balance" in pkg.evidence_ids
    bal_ev = pkg.get_evidence_by_id("ev_cashflow_starting_balance")
    assert bal_ev.value == D("50000.00")
    assert bal_ev.unit == "BDT"

    # Month 0 scheduled expenses should be at least the bill (1200 BDT)
    m0_sched = pkg.get_evidence_by_id("ev_cashflow_month_0_scheduled_expenses")
    assert m0_sched is not None
    assert m0_sched.value == D("1200.00")


def test_cashflow_missing_account_balance(db_session, users):
    u1, _ = users
    # User has transactions but no account balance
    db_session.add(Transaction(user_id=u1.id, date=DAY, amount=D("1000.00"), category="Income"))
    db_session.commit()

    question = "What is my projected balance?"
    route = route_financial_coach_question(question)
    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)

    assert pkg.requires_clarification
    assert "starting_balance" in pkg.missing_data


def test_affordability_evidence(db_session, users):
    u1, _ = users
    seed_user_finances(db_session, u1)

    question = "Can I afford to purchase 15000 BDT?"
    route = route_financial_coach_question(question)
    assert route.intent == CoachIntent.AFFORDABILITY
    assert route.extracted_amount == D("15000")

    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)
    assert not pkg.requires_clarification
    assert "ev_affordability_purchase_amount" in pkg.evidence_ids
    assert "ev_affordability_starting_balance" in pkg.evidence_ids
    assert "ev_affordability_status" in pkg.evidence_ids

    status_ev = pkg.get_evidence_by_id("ev_affordability_status")
    assert status_ev.evidence_type == EvidenceType.INTERPRETATION
    # Balance 50,000, purchase 15,000, reserve 1,200, buffer 5,000 -> recommended
    assert status_ev.value in ("recommended", "caution")


def test_affordability_missing_amount(db_session, users):
    u1, _ = users
    seed_user_finances(db_session, u1)

    question = "Can I afford to purchase a laptop?"
    route = route_financial_coach_question(question)
    assert route.intent == CoachIntent.AFFORDABILITY
    assert route.extracted_amount is None

    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)
    assert pkg.requires_clarification
    assert "purchase_amount" in pkg.missing_data


def test_goal_planning_evidence(db_session, users):
    u1, _ = users
    seed_user_finances(db_session, u1)

    question = "How is my savings goal progress?"
    route = route_financial_coach_question(question)
    assert route.intent == CoachIntent.GOAL_PLANNING

    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)
    assert not pkg.requires_clarification
    assert "ev_goals_active_count" in pkg.evidence_ids
    assert "ev_goals_total_target_amount" in pkg.evidence_ids
    target_ev = pkg.get_evidence_by_id("ev_goals_total_target_amount")
    assert target_ev.value == D("60000.00")
    assert target_ev.unit == "BDT"


def test_financial_health_evidence(db_session, users):
    u1, _ = users
    seed_user_finances(db_session, u1)

    question = "How healthy are my finances?"
    route = route_financial_coach_question(question)
    assert route.intent == CoachIntent.FINANCIAL_HEALTH

    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)
    assert not pkg.requires_clarification
    assert "ev_health_status" in pkg.evidence_ids
    assert "ev_health_coverage_percent" in pkg.evidence_ids


def test_alert_explanation_evidence(db_session, users):
    u1, _ = users
    alert = FinancialAlert(
        user_id=u1.id,
        alert_key="spending_surge_food_2026_11",
        alert_type="spending_surge",
        severity="high",
        title="Unusual dining spending",
        title_key="alerts.spending_surge.title",
        message="Your food spending is 30% higher than average.",
        message_key="alerts.spending_surge.message",
        recommended_action="Review dining budget.",
        status="active",
        created_at=NOW,
    )
    db_session.add(alert)
    db_session.commit()

    question = "Explain this alert"
    route = route_financial_coach_question(question)
    assert route.intent == CoachIntent.ALERT_EXPLANATION

    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)
    assert not pkg.requires_clarification
    assert "ev_alerts_active_count" in pkg.evidence_ids
    assert f"ev_alert_{alert.id}_details" in pkg.evidence_ids


def test_general_finance_evidence(db_session, users):
    u1, _ = users
    question = "What is a budget?"
    route = route_financial_coach_question(question)
    assert route.intent == CoachIntent.GENERAL_FINANCE

    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)
    assert not pkg.requires_clarification
    assert "ev_general_budgeting_rule" in pkg.evidence_ids
    ev = pkg.get_evidence_by_id("ev_general_budgeting_rule")
    assert ev.source == "financial_education"


def test_unknown_or_conflicting_question(db_session, users):
    u1, _ = users
    question = "Tell me a joke about stocks"
    route = route_financial_coach_question(question)
    assert route.intent == CoachIntent.UNKNOWN
    assert route.requires_clarification

    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)
    assert pkg.requires_clarification
    assert pkg.clarification_prompt is not None


def test_date_parser_variations():
    start, end, amb = parse_question_date_period("how much in 2026-10-01 to 2026-10-15?", DAY)
    assert not amb
    assert start == date(2026, 10, 1)
    assert end == date(2026, 10, 15)

    start, end, amb = parse_question_date_period("spending yesterday", DAY)
    assert not amb
    assert start == DAY - timedelta(days=1)
    assert end == DAY - timedelta(days=1)

    start, end, amb = parse_question_date_period("spending last month", DAY)
    assert not amb
    assert start == date(2026, 10, 1)
    assert end == date(2026, 10, 31)

    # Invalid range: start > end
    start, end, amb = parse_question_date_period(
        "spending", DAY, explicit_start=date(2026, 11, 10), explicit_end=date(2026, 11, 1)
    )
    assert amb


def test_missing_income_records(db_session, users):
    u1, _ = users
    # User has recorded expenses only, no income
    db_session.add(Transaction(user_id=u1.id, date=DAY, amount=-D("3500.00"), category="Groceries"))
    db_session.commit()

    question = "How much did I spend this month?"
    route = route_financial_coach_question(question)
    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)

    tot_exp = pkg.get_evidence_by_id("ev_spending_total_expenses")
    tot_inc = pkg.get_evidence_by_id("ev_spending_total_income")
    net_sav = pkg.get_evidence_by_id("ev_spending_net_savings")

    assert tot_exp is not None and tot_exp.value == D("3500.00")
    assert tot_inc is not None and tot_inc.value == D("0.00")
    assert net_sav is not None and net_sav.value == -D("3500.00")


def test_conflicting_intents_clarification(db_session, users):
    u1, _ = users
    # Question with conflicting signals
    question = "Compare these scenarios and can I afford 5000 BDT?"
    route = route_financial_coach_question(question)
    assert route.requires_clarification
    assert len(route.matched_signals) > 1

    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)
    assert pkg.requires_clarification
    assert "multiple topics" in (pkg.clarification_prompt or "")


def test_no_llm_invoked_during_assembly(monkeypatch, db_session, users):
    u1, _ = users
    seed_user_finances(db_session, u1)

    # Monkeypatch langchain_openai or provider structured_optional to fail if called
    def boom(*args, **kwargs):
        raise AssertionError("LLM was invoked during deterministic evidence assembly!")

    monkeypatch.setattr("app.services.ai.provider.structured_optional", boom)

    question = "Where does my money go this month?"
    route = route_financial_coach_question(question)
    pkg = assemble_financial_evidence(db_session, u1.id, route, question, as_of=DAY)
    assert pkg.intent == CoachIntent.SPENDING_ANALYSIS

