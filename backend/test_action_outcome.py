"""AI-15I observable before/after outcomes without financial side effects."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.dependencies import get_current_user
from app.main import app
from app.models import Account, SavingsGoal
from app.models.coaching_feedback import CoachingFeedback
from app.schemas.coaching import CoachingFeedbackInput
from app.services.finance.action_outcome import (
    MIN_FOLLOW_UP_DAYS,
    action_outcomes,
)
from app.services.finance.coaching import financial_coaching
from app.services.finance.coaching_feedback import submit
from app.services.finance.obligation_reconciliation import confirm
from app.services.intelligence.signals import stable_category_token
from backend.test_coaching_feedback import client  # noqa: F401
from backend.test_financial_runway import (
    AS_OF,
    data,  # noqa: F401
    history,
    plan,
    transaction,
)

D = Decimal
ACTION = date(2026, 10, 1)
ACTION_AT = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr("app.services.finance.action_outcome.today_dhaka", lambda: AS_OF)


def acted(db, user, recommendation_id, when=ACTION_AT):
    row = CoachingFeedback(
        user_id=user.id, recommendation_id=recommendation_id,
        evidence_key="a" * 64, status="acted_on",
        created_at=when, updated_at=when)
    db.add(row)
    db.commit()
    return row


def spending_id(kind, category, month="2026-10"):
    return f"{kind}:{stable_category_token(category)}:{month}"


def seed_category(db, user, category, baseline, follow_up):
    first, second = baseline
    transaction(db, user, amount="-" + str(first),
                day=date(2026, 9, 10), category=category)
    transaction(db, user, amount="-" + str(second),
                day=date(2026, 9, 25), category=category)
    first, second = follow_up
    transaction(db, user, amount="-" + str(first),
                day=date(2026, 10, 10), category=category)
    transaction(db, user, amount="-" + str(second),
                day=date(2026, 10, 20), category=category)


def single(data, **kwargs):
    db, users, _ = data
    report = action_outcomes(db, users[0].id, as_of=kwargs.pop("as_of", AS_OF), **kwargs)
    assert report.summary.tracked == len(report.items) == 1
    return report.items[0]


def test_improved_spending_outcome(data):
    db, users, _ = data
    seed_category(db, users[0], "Food", ("9000", "9500"), ("7000", "8200"))
    acted(db, users[0], spending_id("spending_spike", "Food"))
    item = single(data)
    assert item.recommendation_id == spending_id("spending_spike", "Food")
    assert item.recommendation_type == "spending_spike"
    assert item.subject == "Food" and item.status == "improved"
    assert item.metric == "category_spending" and item.direction == "lower_is_better"
    assert item.baseline.start == date(2026, 9, 2)
    assert item.baseline.end == ACTION
    assert item.follow_up.start == date(2026, 10, 2)
    assert item.follow_up.end == date(2026, 10, 31)
    assert item.baseline_value == D("18500.00")
    assert item.follow_up_value == D("15200.00")
    assert item.absolute_change == D("-3300.00")
    assert item.percentage_change == D("-17.84")
    assert item.interpretation == "decreased"
    assert item.causal_claim is False
    assert item.evidence.category == "Food"
    assert item.evidence.baseline_transaction_count == 2
    assert item.evidence.follow_up_transaction_count == 2
    assert item.evidence.currency == "BDT"
    assert any("does not establish" in line for line in item.limitations)


def test_unchanged_spending_outcome(data):
    db, users, _ = data
    seed_category(db, users[0], "Food", ("6000", "4000"), ("5000", "5000"))
    acted(db, users[0], spending_id("spending_spike", "Food"))
    item = single(data)
    assert item.status == "unchanged" and item.interpretation == "unchanged"
    assert item.absolute_change == D("0.00")
    assert item.percentage_change == D("0.00")


def test_worsened_spending_outcome(data):
    db, users, _ = data
    seed_category(db, users[0], "Food", ("6000", "4000"), ("8000", "5000"))
    acted(db, users[0], spending_id("spending_spike", "Food"))
    item = single(data)
    assert item.status == "worsened" and item.interpretation == "increased"
    assert item.absolute_change == D("3000.00")
    assert item.percentage_change == D("30.00")


def test_zero_baseline_does_not_divide_by_zero(data):
    db, users, _ = data
    transaction(db, users[0], amount="5000", day=date(2026, 9, 10), category="Income")
    transaction(db, users[0], amount="-3000", day=date(2026, 10, 10), category="Food")
    acted(db, users[0], spending_id("spending_spike", "Food"))
    item = single(data)
    assert item.baseline_value == D("0.00")
    assert item.follow_up_value == D("3000.00")
    assert item.absolute_change == D("3000.00")
    assert item.percentage_change is None
    # Higher spending is worse for this metric.
    assert item.status == "worsened"


def test_pending_until_minimum_follow_up(data):
    db, users, _ = data
    seed_category(db, users[0], "Food", ("1000", "1000"), ("1000", "1000"))
    recent = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
    acted(db, users[0], spending_id("spending_spike", "Food"), when=recent)
    item = single(data)
    assert item.status == "pending" and item.interpretation == "pending"
    assert item.baseline_value is item.follow_up_value is None
    assert item.absolute_change is item.percentage_change is None
    assert (AS_OF - date(2026, 10, 29)).days < MIN_FOLLOW_UP_DAYS
    assert any("minimum 7-day" in line for line in item.limitations)


def test_repeated_spending_outcome(data):
    db, users, _ = data
    seed_category(db, users[0], "Food", ("6000", "4000"), ("5000", "4000"))
    acted(db, users[0], spending_id("repeated_spending", "Food"))
    item = single(data)
    assert item.recommendation_type == "repeated_spending"
    assert item.subject == "Food" and item.status == "improved"
    assert item.evidence.baseline_transaction_count == 2
    assert item.evidence.follow_up_transaction_count == 2


def test_savings_outcome_uses_recorded_net_cashflow(data):
    db, users, _ = data
    transaction(db, users[0], amount="20000", day=date(2026, 9, 10), category="Income")
    transaction(db, users[0], amount="-15000", day=date(2026, 9, 20), category="Shopping")
    transaction(db, users[0], amount="20000", day=date(2026, 10, 10), category="Income")
    transaction(db, users[0], amount="-12000", day=date(2026, 10, 20), category="Shopping")
    acted(db, users[0], "savings_opportunity:unassigned:2026-10")
    item = single(data)
    assert item.recommendation_type == "savings_opportunity"
    assert item.metric == "recorded_net_cashflow"
    assert item.baseline_value == D("5000.00")
    assert item.follow_up_value == D("8000.00")
    assert item.absolute_change == D("3000.00")
    assert item.status == "improved"
    assert any("not proof that money was transferred" in line for line in item.limitations)


def test_negative_baseline_percentage_uses_absolute_value(data):
    db, users, _ = data
    transaction(db, users[0], amount="10000", day=date(2026, 9, 10), category="Income")
    transaction(db, users[0], amount="-11000", day=date(2026, 9, 20), category="Shopping")
    transaction(db, users[0], amount="10000", day=date(2026, 10, 10), category="Income")
    transaction(db, users[0], amount="-9500", day=date(2026, 10, 20), category="Shopping")
    acted(db, users[0], "savings_opportunity:unassigned:2026-10")
    item = single(data)
    assert item.baseline_value == D("-1000.00")
    assert item.follow_up_value == D("500.00")
    assert item.absolute_change == D("1500.00")
    assert item.percentage_change == D("150.00")
    assert item.status == "improved"


def test_goal_outcome_is_explicitly_insufficient(data):
    db, users, _ = data
    goal = SavingsGoal(user_id=users[0].id, name="Emergency reserve",
                       target_amount=D("50000"), current_saved=D("0"),
                       target_date=date(2026, 12, 1))
    db.add(goal)
    db.commit()
    acted(db, users[0], f"goal_risk:{goal.id}:2026-10")
    item = single(data)
    assert item.recommendation_type == "goal_risk"
    assert item.subject == "Emergency reserve"
    assert item.status == "insufficient_data"
    assert item.interpretation == "goal_history_unavailable"
    assert item.baseline_value is item.follow_up_value is None
    assert any("historical contribution" in line for line in item.limitations)


@pytest.mark.parametrize("allocation,remaining,settlement,percentage", [
    ("6000", "9000", "partially_settled", "-40.00"),
    ("15000", "0", "fully_settled", "-100.00"),
])
def test_obligation_outcome_uses_authoritative_settlement(
        data, allocation, remaining, settlement, percentage):
    db, users, _ = data
    item = plan(db, users[0], amount="15000", due=date(2026, 10, 15))
    tx = transaction(db, users[0], amount="-" + allocation,
                     day=date(2026, 10, 5))
    confirm(db, users[0].id, item.id, tx.id,
            full=D(allocation) == D("15000"))
    from app.models.obligation_allocation import ObligationAllocation
    db.query(ObligationAllocation).one().confirmed_at = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    db.commit()
    acted(db, users[0], f"upcoming_obligations:{item.id}")
    outcome = single(data)
    assert outcome.recommendation_type == "upcoming_obligations"
    assert outcome.baseline_value == D("15000.00")
    assert outcome.follow_up_value == D(remaining + ".00")
    assert outcome.absolute_change == D("-" + allocation + ".00")
    assert outcome.percentage_change == D(percentage)
    assert outcome.settlement_status == settlement
    assert outcome.status == "improved"
    assert outcome.evidence.obligations[0].item_id == item.id
    assert outcome.evidence.obligations[0].allocated_amount == D(allocation + ".00")
    assert outcome.evidence.obligations[0].remaining_amount == D(remaining + ".00")


def test_obligation_not_settled_is_unchanged(data):
    db, users, _ = data
    item = plan(db, users[0], amount="15000", due=date(2026, 10, 15))
    acted(db, users[0], f"upcoming_obligations:{item.id}")
    outcome = single(data)
    assert outcome.settlement_status == "not_settled"
    assert outcome.interpretation == "obligation_not_settled"
    assert outcome.status == "unchanged"
    assert outcome.absolute_change == D("0.00")


def test_cash_risk_outcome_reuses_runway(data):
    db, users, account = data
    account.opening_balance = D("30000")
    account.opening_balance_date = date(2026, 7, 1)
    db.commit()
    for month in (7, 8, 9):
        transaction(db, users[0], amount="3000", day=date(2026, month, 2),
                    category="Income")
        transaction(db, users[0], amount="-1000", day=date(2026, month, 3),
                    category="Utilities")
    transaction(db, users[0], amount="10000", day=date(2026, 10, 15),
                category="Income")
    acted(db, users[0], "cash_risk:2026-10-01:2026-10-31")
    item = single(data)
    assert item.recommendation_type == "cash_risk"
    assert item.metric == "minimum_projected_balance"
    assert item.status == "improved" and item.interpretation == "increased"
    assert item.baseline_value is not None and item.follow_up_value is not None
    assert item.follow_up_value > item.baseline_value
    assert item.evidence.baseline_runway_status == "positive"
    assert item.evidence.follow_up_runway_status == "positive"
    assert item.evidence_quality == "estimated"


def test_cash_risk_insufficient_data_is_not_a_failure(data):
    db, users, _ = data
    acted(db, users[0], "cash_risk:2026-10-01:2026-10-31")
    item = single(data)
    assert item.status == "insufficient_data"
    assert item.interpretation == "insufficient_data"
    assert item.baseline_value is item.follow_up_value is None


def test_mixed_currency_evidence_is_not_compared(data):
    db, users, _ = data
    usd = Account(user_id=users[0].id, name="USD", currency="USD",
                  current_balance=D("999999"))
    db.add(usd)
    db.commit()
    seed_category(db, users[0], "Food", ("6000", "4000"), ("5000", "5000"))
    transaction(db, users[0], usd, amount="-900000",
                day=date(2026, 9, 12), category="Food")
    transaction(db, users[0], usd, amount="-900000",
                day=date(2026, 10, 12), category="Food")
    acted(db, users[0], spending_id("spending_spike", "Food"))
    item = single(data)
    assert item.baseline_value == D("10000.00")
    assert item.follow_up_value == D("10000.00")
    assert item.status == "unchanged"
    assert item.evidence.currency == "BDT"


def test_owner_isolation_and_client_user_id_ignored(data):
    db, users, _ = data
    seed_category(db, users[0], "Food", ("6000", "4000"), ("5000", "5000"))
    key = spending_id("spending_spike", "Food")
    acted(db, users[0], key)
    assert action_outcomes(db, users[1].id, as_of=AS_OF).items == []
    with pytest.raises(HTTPException) as error:
        action_outcomes(db, users[1].id, as_of=AS_OF, recommendation_id=key)
    assert error.value.status_code == 404


def test_api_is_authenticated_and_user_scoped(data, client):
    db, users, _ = data
    seed_category(db, users[0], "Food", ("6000", "4000"), ("5000", "5000"))
    key = spending_id("spending_spike", "Food")
    acted(db, users[0], key)
    overrides = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    try:
        with TestClient(app) as anonymous:
            assert anonymous.get("/finance/action-outcomes").status_code == 401
    finally:
        app.dependency_overrides.update(overrides)
    body = client.get("/finance/action-outcomes").json()
    assert body["summary"]["tracked"] == 1
    assert body["items"][0]["recommendation_id"] == key
    assert body == client.get("/finance/action-outcomes").json()
    app.dependency_overrides[get_current_user] = lambda: users[1]
    other = client.get(
        "/finance/action-outcomes?user_id=" + str(users[0].id)).json()
    assert other["items"] == [] and other["summary"]["tracked"] == 0
    assert client.get(
        "/finance/action-outcomes?recommendation_id=" + key).status_code == 404


def test_filters_and_unsupported_identity(data):
    db, users, _ = data
    seed_category(db, users[0], "Food", ("6000", "4000"), ("5000", "4000"))
    acted(db, users[0], spending_id("spending_spike", "Food"))
    acted(db, users[0], "unknown_kind:abc")
    report = action_outcomes(db, users[0].id, as_of=AS_OF)
    assert report.summary.tracked == 1
    only_improved = action_outcomes(
        db, users[0].id, as_of=AS_OF, status="improved")
    assert len(only_improved.items) == 1
    empty = action_outcomes(db, users[0].id, as_of=AS_OF, status="worsened")
    assert empty.items == [] and empty.summary.tracked == 0


def test_unknown_category_is_insufficient_not_invented(data):
    db, users, _ = data
    acted(db, users[0], "spending_spike:" + "0" * 12 + ":2026-10")
    item = single(data)
    assert item.status == "insufficient_data"
    assert item.evidence.category is None
    assert any("could not be recovered" in line for line in item.limitations)


def test_no_financial_mutation_and_decimal_values(data):
    db, users, _ = data
    seed_category(db, users[0], "Food", ("6000", "4000"), ("5000", "5000"))
    acted(db, users[0], spending_id("spending_spike", "Food"))
    statements = []

    def capture(conn, cursor, statement, params, context, many):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        report = action_outcomes(db, users[0].id, as_of=AS_OF)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert statements == []
    assert not db.new and not db.dirty and not db.deleted
    item = report.items[0]
    assert isinstance(item.baseline_value, Decimal)
    assert isinstance(item.absolute_change, Decimal)
    assert report.model_dump_json() == action_outcomes(
        db, users[0].id, as_of=AS_OF).model_dump_json()


def test_summary_counts_each_classification(data):
    db, users, _ = data
    seed_category(db, users[0], "Food", ("6000", "4000"), ("5000", "5000"))
    acted(db, users[0], spending_id("spending_spike", "Food"))
    transaction(db, users[0], amount="5000", day=date(2026, 9, 12),
                category="Income")
    transaction(db, users[0], amount="20000", day=date(2026, 10, 12),
                category="Income")
    transaction(db, users[0], amount="-1000", day=date(2026, 10, 13),
                category="Shopping")
    acted(db, users[0], "savings_opportunity:unassigned:2026-10")
    recent = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
    acted(db, users[0], spending_id("repeated_spending", "Food"), when=recent)
    report = action_outcomes(db, users[0].id, as_of=AS_OF)
    summary = report.summary
    assert summary.tracked == 3
    assert summary.improved == 1 and summary.pending == 1
    assert summary.improved + summary.unchanged + summary.worsened + \
        summary.pending + summary.insufficient_data == summary.tracked


def test_api_validation(data, client):
    for query in ("status=unknown", "status=observed"):
        assert client.get("/finance/action-outcomes?" + query).status_code == 422
    assert client.get("/finance/action-outcomes?recommendation_id=missing").status_code == 404


def test_acted_on_feedback_created_through_existing_api_is_tracked(
        data, client, monkeypatch):
    db, users, _ = data
    # Three complete months let the generator emit a real spending review.
    transaction(db, users[0], amount="-1000", day=date(2026, 8, 10),
                category="Food")
    transaction(db, users[0], amount="-2000", day=date(2026, 9, 10),
                category="Food")
    transaction(db, users[0], amount="-5000", day=date(2026, 10, 10),
                category="Food")
    generated = financial_coaching(db, users[0].id, as_of=AS_OF)
    spending = next(item for item in generated.recommendations
                    if item.type in {"spending_spike", "repeated_spending"})

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return ACTION_AT if tz is not None else ACTION_AT.replace(tzinfo=None)

    monkeypatch.setattr(
        "app.services.finance.coaching_feedback.datetime", FrozenDatetime)
    submit(db, users[0].id, spending.id,
           CoachingFeedbackInput(status="acted_on"), as_of=AS_OF)
    report = client.get("/finance/action-outcomes").json()
    assert report["summary"]["tracked"] == 1
    assert report["items"][0]["recommendation_id"] == spending.id
    assert report["items"][0]["action_reported_on"] == str(ACTION)
    assert report["items"][0]["status"] == "worsened"


@pytest.mark.parametrize("before_action,expected", [(True, "unchanged"), (False, "improved")])
def test_obligation_allocations_respect_action_timestamp(data, before_action, expected):
    from app.models.obligation_allocation import ObligationAllocation
    db, users, _ = data
    item = plan(db, users[0], amount="15000", due=date(2026, 10, 15))
    tx = transaction(db, users[0], amount="-6000", day=date(2026, 10, 5))
    confirm(db, users[0].id, item.id, tx.id)
    allocation = db.query(ObligationAllocation).one()
    allocation.confirmed_at = datetime(2026, 9, 30, 12, tzinfo=timezone.utc) if before_action else datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    db.commit()
    acted(db, users[0], f"upcoming_obligations:{item.id}")
    outcome = single(data)
    assert outcome.status == expected
    assert outcome.baseline_value == D("9000" if before_action else "15000")
    assert outcome.follow_up_value == D("9000")
    assert outcome.absolute_change == D("0" if before_action else "-6000")


def test_revoked_obligation_allocation_can_worsen_outcome(data):
    from app.models.obligation_allocation import ObligationAllocation
    db, users, _ = data
    item = plan(db, users[0], amount="15000", due=date(2026, 10, 15))
    tx = transaction(db, users[0], amount="-6000", day=date(2026, 9, 29))
    confirm(db, users[0].id, item.id, tx.id)
    allocation = db.query(ObligationAllocation).one()
    allocation.confirmed_at = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    allocation.active = False
    allocation.revoked_at = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    db.commit()
    acted(db, users[0], f"upcoming_obligations:{item.id}")
    outcome = single(data)
    assert outcome.baseline_value == D("9000")
    assert outcome.follow_up_value == D("15000")
    assert outcome.status == "worsened"


def test_spending_uses_original_evidence_month_after_recommendation_expires(data):
    db, users, _ = data
    transaction(db, users[0], amount="-20000", day=date(2026, 9, 10), category="Food")
    transaction(db, users[0], amount="-15000", day=date(2026, 10, 15), category="Food")
    key = spending_id("spending_spike", "Food", "2026-09")
    acted(db, users[0], key)
    item = single(data)
    assert item.baseline.start == date(2026, 9, 1)
    assert item.baseline.end == date(2026, 9, 30)
    assert item.follow_up.start == date(2026, 10, 2)
    assert item.follow_up.days == item.baseline.days == 30
    assert item.absolute_change == D("-5000")
    assert item.percentage_change == D("-25")
    assert item.status == "improved"


def test_full_month_baseline_waits_for_equal_follow_up(data):
    db, users, _ = data
    transaction(db, users[0], amount="-20000", day=date(2026, 9, 10), category="Food")
    acted(db, users[0], spending_id("spending_spike", "Food", "2026-09"))
    item = single(data, as_of=date(2026, 10, 10))
    assert item.status == "pending"
    assert not item.follow_up.is_complete
    assert item.baseline_value is item.follow_up_value is None


def test_future_action_is_not_observed(data):
    db, users, _ = data
    acted(db, users[0], "savings_opportunity:unassigned:2026-12",
          when=datetime(2026, 12, 1, tzinfo=timezone.utc))
    assert action_outcomes(db, users[0].id, as_of=AS_OF).items == []


def test_no_bdt_history_is_insufficient_for_savings(data):
    db, users, _ = data
    acted(db, users[0], "savings_opportunity:unassigned:2026-10")
    item = single(data)
    assert item.status == "insufficient_data"
    assert item.baseline_value is item.follow_up_value is None


@pytest.mark.parametrize("before,after,change,percentage,status", [
    ("20000", "15000", "-5000", "-25.00", "improved"),
    ("10000", "10000", "0", "0.00", "unchanged"),
    ("10000", "13000", "3000", "30.00", "worsened"),
    ("0", "3000", "3000", None, "worsened"),
])
def test_offline_evaluation_plain_arithmetic_ground_truth(data, before, after, change, percentage, status):
    # Independently specified arithmetic, evaluated through the real read model.
    db, users, _ = data
    transaction(db, users[0], amount="50000", day=date(2026, 9, 1), category="Income")
    transaction(db, users[0], amount="-" + before, day=date(2026, 9, 10), category="Food")
    transaction(db, users[0], amount="-" + after, day=date(2026, 10, 10), category="Food")
    acted(db, users[0], spending_id("spending_spike", "Food", "2026-09"))
    item = single(data)
    assert item.absolute_change == D(change)
    assert item.percentage_change == (D(percentage) if percentage is not None else None)
    assert item.status == status


def test_cash_outcome_declines_unreconstructable_obligation_history(data):
    db, users, _ = data
    scheduled = plan(db, users[0], amount="15000")
    scheduled.updated_at = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    db.commit()
    acted(db, users[0], "cash_risk:2026-10-01:2026-10-31")
    item = single(data)
    assert item.status == "insufficient_data"
    assert item.baseline_value is item.follow_up_value is None
