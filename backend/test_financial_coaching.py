"""AI-15F deterministic recommendations and evidence, without financial side effects."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models import Account, SavingsGoal, Transaction
from app.schemas.coach import GoalCreate
from app.schemas.coaching import FinancialCoaching
from app.services.finance.coaching import financial_coaching, goal_recommendation
from app.services.finance.obligation_reconciliation import confirm, revoke
from app.services.intelligence.snapshot import monthly_history
from app.services.intelligence.facts import totals
from backend.test_financial_runway import data, plan, transaction, history, AS_OF  # noqa: F401

D = Decimal


def read(data, **kw):
    db, users, _ = data
    return financial_coaching(db, users[0].id, as_of=AS_OF, **kw)


def of(result, kind):
    return [r for r in result.recommendations if r.type == kind]


def category_history(db, user, category="Food", amounts=("100", "200", "350"), income="3000"):
    for month, amount in zip((8, 9, 10), amounts):
        transaction(db, user, amount=income, day=date(2026, month, 2), category="Income")
        transaction(db, user, amount="-" + amount, day=date(2026, month, 3), category=category)


def goal(db, user, target="50000", saved="0", due=date(2026, 12, 1)):
    row = SavingsGoal(user_id=user.id, name="Emergency reserve", target_amount=D(target), current_saved=D(saved) if saved else None, target_date=due)
    db.add(row); db.commit()
    return row


def test_cash_shortfall_uses_existing_runway_evidence(data):
    db, users, account = data
    account.opening_balance = D("500"); db.commit()
    history(db, users[0], income="2000", expense="1000")
    item = of(read(data), "cash_risk")[0]
    assert item.priority == "critical"
    assert item.evidence.runway_mode == "historical"
    assert item.evidence.minimum_projected_balance < 0
    assert item.evidence.first_shortfall_date is None
    assert item.evidence.first_shortfall_period is not None
    assert item.amount is None and item.source == "financial_runway"
    assert item.assumptions and item.limitations
    assert not of(read(data), "savings_opportunity")


@pytest.mark.parametrize("threshold,priority", [("0", "high"), ("500", "high")])
def test_approaching_threshold_and_known_obligations_without_history(data, threshold, priority):
    db, users, account = data
    account.opening_balance = D("1000"); db.commit()
    plan(db, users[0], amount="1000" if threshold == "0" else "600")
    risk = of(read(data, safety_threshold=D(threshold)), "cash_risk")[0]
    assert risk.priority == priority and risk.evidence.runway_mode == "known_obligations"
    assert risk.evidence_quality == "limited"


def test_known_obligation_shortfall_is_deduplicated_against_historical(data):
    db, users, account = data
    account.opening_balance = D("1000"); db.commit()
    history(db, users[0])
    plan(db, users[0], amount="2000")
    risks = of(read(data), "cash_risk")
    assert len(risks) == 1 and risks[0].priority == "critical"
    assert risks[0].evidence.runway_mode == "known_obligations"
    assert risks[0].evidence.first_shortfall_date == AS_OF


def test_large_future_obligation_relative_to_cash(data):
    db, users, _ = data
    plan(db, users[0], amount="16000", due=AS_OF + timedelta(days=20))
    alert = of(read(data), "upcoming_obligations")[0]
    assert alert.amount == 16000
    assert alert.evidence.obligations[0].due_date == AS_OF + timedelta(days=20)
    assert alert.evidence.obligations[0].timeline_event_id.startswith("obligation:")


@pytest.mark.parametrize("allocation,remaining", [("0", "15000"), ("6000.25", "8999.75"), ("15000", "0")])
def test_obligations_use_remaining_and_preserve_transactions(data, allocation, remaining):
    db, users, account = data
    item = plan(db, users[0])
    if D(allocation):
        tx = transaction(db, users[0], account, amount="-" + allocation)
        confirm(db, users[0].id, item.id, tx.id)
    alerts = of(read(data), "upcoming_obligations")
    if D(remaining):
        assert len(alerts) == 1 and alerts[0].amount == D(remaining)
        breakdown = alerts[0].evidence.obligations[0]
        assert breakdown.original_amount == 15000
        assert breakdown.allocated_amount == D(allocation)
        assert breakdown.remaining_amount == D(remaining)
    else:
        assert alerts == []
    assert item.amount == 15000
    assert db.query(Transaction).count() == (1 if D(allocation) else 0)


def test_revocation_and_candidates(data):
    db, users, account = data
    item = plan(db, users[0])
    tx = transaction(db, users[0], account, amount="-6000")
    assert of(read(data), "upcoming_obligations")[0].amount == 15000
    confirm(db, users[0].id, item.id, tx.id)
    assert of(read(data), "upcoming_obligations")[0].amount == 9000
    revoke(db, users[0].id, item.id, tx.id)
    assert of(read(data), "upcoming_obligations")[0].amount == 15000


def test_cluster_has_one_recommendation_with_all_remaining_amounts(data):
    db, users, _ = data
    for day in [0, 2, 7]:
        plan(db, users[0], amount="100.25", due=AS_OF + timedelta(days=day))
    result = of(read(data), "upcoming_obligations")
    assert len(result) == 1 and result[0].amount == D("300.75")
    assert len(result[0].evidence.obligations) == 3
    assert result[0].priority == "high"


@pytest.mark.parametrize("status", ["paid", "cancelled"])
def test_terminal_obligations_not_presented_as_unpaid(data, status):
    db, users, _ = data
    plan(db, users[0], status=status)
    assert not of(read(data), "upcoming_obligations")


def test_spending_spike_uses_complete_periods(data):
    db, users, _ = data
    category_history(db, users[0], category="Utilities", amounts=("100", "100", "200"))
    item = of(read(data), "spending_spike")[0]
    assert item.evidence.observed_value == 200 and item.evidence.reference_value == 100
    assert item.evidence.percentage_change == 100
    assert item.evidence.period.start == date(2026, 10, 1)
    assert item.evidence.period.is_complete and item.evidence.comparison_period.is_complete
    assert item.amount is None


def test_no_spike_without_three_complete_months_or_current_month_extrapolation(data):
    db, users, _ = data
    transaction(db, users[0], amount="-999999", category="Utilities", day=AS_OF)
    assert not of(read(data), "spending_spike")
    category_history(db, users[0], category="Utilities", amounts=("100", "100", "100"))
    assert not of(read(data), "spending_spike")


def test_repeated_discretionary_review_supersedes_duplicate_spike(data):
    db, users, _ = data
    category_history(db, users[0])
    result = read(data)
    repeated = of(result, "repeated_spending")
    assert len(repeated) == 1 and repeated[0].subject == "Food"
    assert len(repeated[0].evidence.monthly_values) == 3
    assert repeated[0].evidence.reference_value == 100
    assert not of(result, "spending_spike")


def test_non_discretionary_categories_do_not_get_repeated_discretionary_claims(data):
    db, users, _ = data
    category_history(db, users[0], category="Medical")
    assert not of(read(data), "repeated_spending")


@pytest.mark.parametrize("classification", ["category", "transaction_type"])
def test_explicit_transfers_do_not_create_spending_or_savings_claims(data, classification):
    db, users, _ = data
    for month, value in zip((8, 9, 10), ("100", "300", "900")):
        values = {"category": "Transfer"} if classification == "category" else {"category": "Food", "transaction_type": "internal_transfer"}
        transaction(db, users[0], amount="-" + value, day=date(2026, month, 2), **values)
    assert not of(read(data), "spending_spike")
    assert not of(read(data), "repeated_spending")
    assert not of(read(data), "savings_opportunity")
    # Existing consumers retain their prior totals and coverage semantics.
    assert totals(db, users[0].id, date(2026, 10, 1), date(2026, 10, 31))["expenses"] == 900
    assert totals(db, users[0].id, date(2026, 10, 1), date(2026, 10, 31), exclude_transfers=True)["expenses"] is None


def test_savings_sustainable_cap_and_uncertain_income_exclusion(data):
    db, users, _ = data
    history(db, users[0], income="3000", expense="1000")
    plan(db, users[0], amount="500", due=AS_OF + timedelta(days=2))
    before = of(read(data), "savings_opportunity")[0]
    assert before.amount == 2000
    assert before.amount <= before.evidence.cash_after_known_obligations
    assert before.amount <= before.evidence.minimum_projected_balance
    plan(db, users[0], kind="income", amount="999999")
    after = of(read(data), "savings_opportunity")[0]
    assert after.amount == before.amount
    assert after.evidence.uncertain_income == 999999
    assert len(of(read(data), "savings_opportunity")) == 1


@pytest.mark.parametrize("condition", ["obligations", "reported_only", "active_goal", "deficit_month", "unknown_cash"])
def test_no_savings_when_evidence_cannot_support_unassigned_cash(data, condition):
    db, users, account = data
    history(db, users[0], income="3000", expense="1000")
    if condition == "obligations": plan(db, users[0], amount="30000")
    if condition == "reported_only":
        account.opening_balance = account.opening_balance_date = None; account.current_balance = D("30000")
    if condition == "active_goal": goal(db, users[0], target="1000")
    if condition == "deficit_month": transaction(db, users[0], amount="-9000", day=date(2026, 8, 5))
    if condition == "unknown_cash": account.opening_balance = account.opening_balance_date = None
    db.commit()
    assert not of(read(data), "savings_opportunity")


def test_goal_risk_uses_existing_planner_without_invented_savings_pattern(data):
    db, users, _ = data
    history(db, users[0])
    saved_goal = goal(db, users[0])
    alert = of(read(data), "goal_risk")[0]
    assert alert.evidence.goal_id == saved_goal.id
    assert alert.evidence.remaining_amount == 50000
    assert alert.evidence.required_monthly == 25000
    assert alert.evidence.estimated_monthly_capacity == 1000
    assert alert.evidence.affordability == "at_risk"
    assert alert.amount is None


def test_missing_goal_target_date_is_not_invented(data):
    db, users, _ = data
    h = monthly_history(db, users[0].id, AS_OF)
    assert goal_recommendation(db, users[0].id, SimpleNamespace(target_date=None), AS_OF, h) is None
    with pytest.raises(ValueError):
        GoalCreate(name="Missing date", target_amount="1000", current_saved="0", target_date=None)


def test_overdue_goal_can_be_reviewed_without_forecast_history(data):
    db, users, _ = data
    goal(db, users[0], due=AS_OF - timedelta(days=1), saved=None)
    alert = of(read(data), "goal_risk")[0]
    assert alert.priority == "high"
    assert alert.evidence.current_saved is alert.evidence.required_monthly is None
    assert alert.evidence.target_date == AS_OF - timedelta(days=1)


def test_empty_and_partial_data_remain_explicit(data):
    db, users, _ = data
    empty = financial_coaching(db, users[1].id, as_of=AS_OF)
    assert empty.recommendations == [] and empty.data_status == "insufficient_data"
    assert read(data).data_status == "partial"
    history(db, users[0], income="1000", expense="1000")
    result = read(data)
    assert result.data_status == "sufficient" and result.recommendations == []


def test_deterministic_order_priorities_and_read_only_owner_scoped_response(data):
    db, users, _ = data
    history(db, users[0])
    plan(db, users[0], amount="50000")
    goal(db, users[0])
    statements = []
    def capture(conn, cursor, statement, params, context, many): statements.append(statement.lstrip().split()[0].upper())
    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        first = read(data)
        assert first.model_dump_json() == read(data).model_dump_json()
    finally: event.remove(db.bind, "before_cursor_execute", capture)
    assert first.recommendations[0].priority == "critical"
    assert len({r.id for r in first.recommendations}) == len(first.recommendations)
    assert not {"INSERT", "UPDATE", "DELETE"} & set(statements)
    assert all(item.evidence.period and item.limitations and item.recommended_action for item in first.recommendations)
    FinancialCoaching.model_validate_json(first.model_dump_json())
    assert read(data, priority="critical").recommendations == [first.recommendations[0]]


def test_cross_user_and_foreign_currency_isolation(data):
    db, users, _ = data
    before = read(data).model_dump_json()
    account = Account(user_id=users[1].id, name="Private account", current_balance=D("999999"))
    usd = Account(user_id=users[0].id, name="USD", currency="USD", current_balance=D("999999"))
    db.add_all([account, usd]); db.commit()
    transaction(db, users[1], account, amount="999999", merchant="Private")
    transaction(db, users[0], usd, amount="999999")
    plan(db, users[1], amount="999999")
    goal(db, users[1])
    assert read(data).model_dump_json() == before
    assert "Private" not in before


def test_api_auth_validation_serialization_isolation_and_repeatability(data, monkeypatch):
    db, users, _ = data
    monkeypatch.setattr("app.services.finance.coaching.today_dhaka", lambda: AS_OF)
    plan(db, users[0], amount="123.45")
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            assert client.get("/finance/coaching").status_code == 401
            app.dependency_overrides[get_current_user] = lambda: users[0]
            for params in [{"priority": "bad"}, {"safety_threshold": "-1"}, {"safety_threshold": "1.001"}]:
                assert client.get("/finance/coaching", params=params).status_code == 422
            response = client.get("/finance/coaching")
            assert response.status_code == 200
            assert response.json() == client.get("/finance/coaching").json()
            assert response.json()["recommendations"][0]["amount"] == "123.45"
            assert client.get("/finance/coaching?priority=critical").json()["recommendations"] == []
            app.dependency_overrides[get_current_user] = lambda: users[1]
            body = client.get("/finance/coaching").json()
            assert body["recommendations"] == [] and body["data_status"] == "insufficient_data"
    finally: app.dependency_overrides.clear()


def test_income_only_history_does_not_establish_sustainable_expense_coverage(data):
    db, users, _ = data
    for month in (8, 9, 10):
        transaction(db, users[0], amount="3000", day=date(2026, month, 2), category="Income")
    assert not of(read(data), "savings_opportunity")


@pytest.mark.parametrize("latest", ["100", "150"])
def test_spike_threshold_is_strict_and_does_not_label_equal_values(data, latest):
    db, users, _ = data
    category_history(db, users[0], category="Utilities", amounts=("100", "100", latest))
    assert not of(read(data), "spending_spike")
