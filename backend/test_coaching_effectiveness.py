"""AI-15J aggregation, scope, and read-only API regression checks."""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import get_args

import pytest
from sqlalchemy import event, select

from app.core.dependencies import get_current_user
from app.core.database import Base
from app.main import app
from app.models.coaching_feedback import CoachingFeedback
from app.schemas.coaching import CoachingType
from app.services.finance.coaching_effectiveness import get_coaching_effectiveness, percentage
from backend.test_coaching_feedback import client  # noqa: F401
from backend.test_financial_runway import data, plan, transaction  # noqa: F401
from backend.test_action_outcome import seed_category, spending_id


def feedback(db, user, key, status="acted_on"):
    row = CoachingFeedback(user_id=user.id, recommendation_id=key, status=status,
        evidence_key="a" * 64, snoozed_until=date(2026, 12, 1) if status == "snoozed" else None,
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    db.add(row)
    db.commit()
    return row


def test_empty(data, client):
    response = client.get("/finance/coaching/effectiveness")
    assert response.status_code == 200
    body = response.json()
    assert set(body["counts"].values()) == {0}
    assert set(body["rates"].values()) == {None}
    assert body["by_type"] == [] and body["causal_claim"] is False
    scoped_limitation = (
        "Outcome observations normally apply only to acted-on recommendations; dismissed, not-relevant, snoozed and unrated recommendations are excluded from outcome tracking. "
        "Dismissed, not-relevant and snoozed feedback are still included in overall feedback totals."
    )
    assert scoped_limitation in body["limitations"]
    from app.services.finance.action_outcome import REPORT_LIMITATIONS
    assert REPORT_LIMITATIONS[0] not in body["limitations"]
    assert all(value in body["limitations"] for value in REPORT_LIMITATIONS[1:])



def test_mixed_lifecycle(data, monkeypatch):
    db, users, _ = data
    statuses = ["acted_on"] * 4 + ["dismissed", "not_relevant", "snoozed"]
    outcomes = ["improved", "unchanged", "worsened", "insufficient_data", "improved", "improved", "improved"]
    items = []
    for n, (status, outcome) in enumerate(zip(statuses, outcomes)):
        key = f"spending_spike:test{n}:2026-10"
        feedback(db, users[0], key, status)
        items.append(SimpleNamespace(recommendation_id=key, status=outcome))
    monkeypatch.setattr("app.services.finance.coaching_effectiveness.action_outcomes",
                        lambda *a, **kw: SimpleNamespace(items=items, limitations=[]))
    result = get_coaching_effectiveness(db, users[0].id)
    assert result.counts.model_dump() == dict(total_recommendations=7, acted_on=4,
        dismissed=1, not_relevant=1, snoozed=1, measurable_outcomes=3,
        improved=1, unchanged=1, worsened=1, insufficient_data=1)
    assert result.rates.model_dump() == dict(observable_outcome_rate=Decimal("75.00"),
        improvement_rate_among_observed=Decimal("33.33"), worsening_rate_among_observed=Decimal("33.33"))


@pytest.mark.parametrize("status", ["pending", "insufficient_data", None])
def test_unobserved_and_zero_denominators(data, monkeypatch, status):
    db, users, _ = data
    key = "goal_risk:1"
    feedback(db, users[0], key)
    items = [] if status is None else [SimpleNamespace(recommendation_id=key, status=status)]
    monkeypatch.setattr("app.services.finance.coaching_effectiveness.action_outcomes",
                        lambda *a, **kw: SimpleNamespace(items=items, limitations=[]))
    result = get_coaching_effectiveness(db, users[0].id)
    assert result.rates.observable_outcome_rate == Decimal("0.00")
    assert result.rates.improvement_rate_among_observed is None
    assert result.rates.worsening_rate_among_observed is None
    assert result.counts.insufficient_data == (1 if status == "insufficient_data" else 0)
    assert percentage(0, 0) is None
    assert percentage(1, 32) == Decimal("3.13")


def test_type_breakdown(data, monkeypatch):
    db, users, _ = data
    items = []
    for kind in get_args(CoachingType):
        key = f"{kind}:test"
        feedback(db, users[0], key)
        items.append(SimpleNamespace(recommendation_id=key, status="improved"))
    monkeypatch.setattr("app.services.finance.coaching_effectiveness.action_outcomes",
                        lambda *a, **kw: SimpleNamespace(items=items, limitations=[]))
    result = get_coaching_effectiveness(db, users[0].id)
    assert [item.recommendation_type for item in result.by_type] == sorted(get_args(CoachingType))
    for name in ("total_recommendations", "acted_on", "improved", "measurable_outcomes"):
        assert sum(getattr(item, name) for item in result.by_type) == getattr(result.counts, name) == 6
    assert all(item.observable_outcome_rate == Decimal("100.00") for item in result.by_type)


def test_real_api_isolation_and_read_only(data, client, monkeypatch):
    db, users, _ = data
    monkeypatch.setattr("app.services.finance.action_outcome.today_dhaka", lambda: date(2026, 10, 31))
    for n, follow_up in enumerate([("100", "100"), ("100", "100"), ("1000", "1000")]):
        category = f"Category{n}"
        seed_category(db, users[0], category, ("500", "500"), follow_up)
        feedback(db, users[0], spending_id("spending_spike", category))
    for n in range(10):
        feedback(db, users[1], f"goal_risk:{n}")
    plan(db, users[0])
    tables = list(Base.metadata.sorted_tables)
    def snapshot():
        return {table.name: [tuple(row) for row in db.execute(select(table)).all()] for table in tables}
    before = snapshot()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        response = client.get("/finance/coaching/effectiveness?user_id=" + str(users[1].id))
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"]["acted_on"] == 3
    assert body["counts"]["improved"] == 2
    assert body["rates"]["improvement_rate_among_observed"] == "66.67"
    assert snapshot() == before
    assert not any(s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for s in statements)
    app.dependency_overrides[get_current_user] = lambda: users[1]
    other = client.get("/finance/coaching/effectiveness").json()
    assert other["counts"]["acted_on"] == 10
    assert other["counts"]["improved"] == 0


def test_authentication_required(client):
    app.dependency_overrides.pop(get_current_user)
    assert client.get("/finance/coaching/effectiveness").status_code == 401


def test_invalid_scope(data):
    with pytest.raises(ValueError):
        get_coaching_effectiveness(data[0], 0)


def test_heterogeneous_type_breakdown(data, monkeypatch):
    db, users, _ = data
    distributions = {
        "spending_spike": [("acted_on", "improved"), ("acted_on", "improved"),
                           ("acted_on", "worsened"), ("acted_on", "insufficient_data"),
                           ("dismissed", None)],
        "cash_risk": [("acted_on", "unchanged"), ("acted_on", "pending"),
                      ("not_relevant", None), ("snoozed", None)],
        "goal_risk": [("acted_on", "insufficient_data"), ("dismissed", None)],
    }
    items = []
    for kind, records in distributions.items():
        for index, (state, outcome) in enumerate(records):
            key = f"{kind}:test{index}"
            feedback(db, users[0], key, state)
            if outcome is not None:
                items.append(SimpleNamespace(recommendation_id=key, status=outcome))
    monkeypatch.setattr("app.services.finance.coaching_effectiveness.action_outcomes",
                        lambda *a, **kw: SimpleNamespace(items=items, limitations=[]))
    result = get_coaching_effectiveness(db, users[0].id)
    assert result.counts.model_dump() == dict(
        total_recommendations=11, acted_on=7, dismissed=2, not_relevant=1, snoozed=1,
        measurable_outcomes=4, improved=2, unchanged=1, worsened=1, insufficient_data=2)
    assert result.rates.model_dump() == dict(
        observable_outcome_rate=Decimal("57.14"),
        improvement_rate_among_observed=Decimal("50.00"),
        worsening_rate_among_observed=Decimal("25.00"))
    actual = {row.recommendation_type: row.model_dump() for row in result.by_type}
    assert actual == {
        "spending_spike": dict(recommendation_type="spending_spike", total_recommendations=5,
            acted_on=4, measurable_outcomes=3, improved=2, unchanged=0, worsened=1,
            insufficient_data=1, observable_outcome_rate=Decimal("75.00"),
            improvement_rate_among_observed=Decimal("66.67"), worsening_rate_among_observed=Decimal("33.33")),
        "cash_risk": dict(recommendation_type="cash_risk", total_recommendations=4,
            acted_on=2, measurable_outcomes=1, improved=0, unchanged=1, worsened=0,
            insufficient_data=0, observable_outcome_rate=Decimal("50.00"),
            improvement_rate_among_observed=Decimal("0.00"), worsening_rate_among_observed=Decimal("0.00")),
        "goal_risk": dict(recommendation_type="goal_risk", total_recommendations=2,
            acted_on=1, measurable_outcomes=0, improved=0, unchanged=0, worsened=0,
            insufficient_data=1, observable_outcome_rate=Decimal("0.00"),
            improvement_rate_among_observed=None, worsening_rate_among_observed=None),
    }
    for field in ("total_recommendations", "acted_on", "measurable_outcomes", "improved", "unchanged", "worsened", "insufficient_data"):
        assert sum(getattr(row, field) for row in result.by_type) == getattr(result.counts, field)
