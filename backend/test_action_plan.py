"""AI-15H compositional ranking, API isolation, visibility and immutability."""
from datetime import timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from app.main import app
from app.core.dependencies import get_current_user
from app.models.coaching_feedback import CoachingFeedback
from app.schemas.coaching import CoachingFeedbackInput
from app.services.finance.coaching import financial_coaching, recommendation
from app.services.finance.coaching_feedback import submit
from app.services.finance.action_plan import action_plan, MAX_ACTIVE_ACTIONS, LIMIT_NOTE
from backend.test_coaching_feedback import data, client, clock  # noqa: F401
from backend.test_financial_runway import plan, AS_OF


def test_authentication():
    with TestClient(app) as client:
        assert client.get("/finance/action-plan").status_code == 401


def test_api_empty_and_validation(data, client):
    response = client.get("/finance/action-plan")
    assert response.status_code == 200
    body = response.json()
    assert body["actions"] == [] and body["completed_count"] == body["active_count"] == 0
    assert body == client.get("/finance/action-plan").json()
    for query in ("priority=urgent", "safety_threshold=-1", "safety_threshold=NaN"):
        assert client.get("/finance/action-plan?" + query).status_code == 422


def test_current_coaching_projection(data, client):
    db, users, _ = data
    plan(db, users[0])
    coaching = financial_coaching(db, users[0].id)
    body = client.get("/finance/action-plan").json()
    assert body["as_of_date"] == str(AS_OF)
    assert body["data_status"] == coaching.data_status
    assert body["active_count"] == len(body["actions"]) == 1
    action = body["actions"][0]
    original = coaching.recommendations[0]
    for field in ("id", "type", "priority", "title", "recommended_action", "currency", "source", "evidence_quality"):
        assert action[field] == getattr(original, field)
    assert action["amount"] == str(original.amount)
    assert action["rank"] == 1 and action["status"] == "active"
    assert action["recommendation_id"] == original.id
    assert "evidence" not in action
    assert body == client.get("/finance/action-plan").json()
    assert client.get("/finance/action-plan?priority=low").json()["actions"] == []


@pytest.mark.parametrize("status", ["dismissed", "acted_on", "not_relevant", "snoozed"])
def test_feedback_visibility_and_completion(data, client, status):
    db, users, _ = data
    plan(db, users[0])
    key = financial_coaching(db, users[0].id).recommendations[0].id
    payload = CoachingFeedbackInput(status=status, snoozed_until=AS_OF + timedelta(days=2) if status == "snoozed" else None)
    submit(db, users[0].id, key, payload)
    result = client.get("/finance/action-plan").json()
    assert result["actions"] == [] and result["active_count"] == 0
    assert result["completed_count"] == (1 if status == "acted_on" else 0)
    if status == "acted_on":
        assert result["completed_feedback"][0]["action_status"] == "reported_done"
        # Like AI-15G history, completion is independent of priority filtering.
        assert client.get("/finance/action-plan?priority=low").json()["completed_count"] == 1


def test_expired_snooze_changed_and_disappeared_evidence(data, client):
    db, users, account = data
    item = plan(db, users[0], due=AS_OF + timedelta(days=4))
    key = financial_coaching(db, users[0].id).recommendations[0].id
    submit(db, users[0].id, key, CoachingFeedbackInput(status="snoozed", snoozed_until=AS_OF + timedelta(days=1)))
    assert key in {a.id for a in action_plan(db, users[0].id, as_of=AS_OF + timedelta(days=1)).actions}
    submit(db, users[0].id, key, CoachingFeedbackInput(status="acted_on"))
    account.opening_balance = Decimal("100")
    db.commit()
    changed = client.get("/finance/action-plan").json()
    assert key in {a["id"] for a in changed["actions"]}
    assert changed["completed_count"] == 0
    item.status = "paid"
    db.commit()
    result = client.get("/finance/action-plan").json()
    assert key not in {a["id"] for a in result["actions"]}
    assert result["completed_feedback"] == []


def test_owner_isolation(data, client):
    db, users, _ = data
    plan(db, users[0]); plan(db, users[1])
    key = financial_coaching(db, users[0].id).recommendations[0].id
    submit(db, users[0].id, key, CoachingFeedbackInput(status="acted_on"))
    own = client.get("/finance/action-plan").json()
    assert own["completed_count"] == 1
    app.dependency_overrides[get_current_user] = lambda: users[1]
    other = client.get("/finance/action-plan?user_id=" + str(users[0].id)).json()
    assert other["completed_count"] == 0 and other["active_count"] == 1
    assert other["actions"][0]["id"] != key
    # Even a colliding recommendation ID across users is unaffected by A's feedback.
    db.add(CoachingFeedback(user_id=users[1].id, recommendation_id=key,
        evidence_key="x" * 64, status="acted_on"))
    db.commit()
    assert client.get("/finance/action-plan").json() == other


def test_threshold_matches_coaching(data, client):
    db, users, _ = data
    for floor in ("0", "30000", "31000"):
        coaching = client.get("/finance/coaching?safety_threshold=" + floor).json()
        result = client.get("/finance/action-plan?safety_threshold=" + floor).json()
        assert {a["id"] for a in result["actions"]} == {a["id"] for a in coaching["recommendations"]}
    assert client.get("/finance/action-plan?safety_threshold=31000").json()["active_count"] > 0


def test_no_writes_to_any_table(data, client):
    db, users, _ = data
    plan(db, users[0])
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            statements.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        assert client.get("/finance/action-plan").status_code == 200
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert statements == [] and not db.new and not db.dirty and not db.deleted


def synthetic(kind, priority, key):
    return recommendation(kind, f"{priority}:{key}", AS_OF, AS_OF + timedelta(days=2), priority=priority,
        source="financial_runway", evidence={"period": {"kind":"test", "start":AS_OF, "end":AS_OF,
        "is_complete":False, "label":"test"}})


def test_ranking_limits_and_stable_ids(data, monkeypatch):
    db, users, _ = data
    generated = financial_coaching(db, users[0].id)
    rows = [synthetic(kind, priority, key) for kind, priority, key in [
        ("savings_opportunity", "low", "a"), ("goal_risk", "medium", "z"),
        ("spending_spike", "medium", "a"), ("repeated_spending", "medium", "z"),
        ("upcoming_obligations", "medium", "z"), ("cash_risk", "medium", "z"),
        ("goal_risk", "high", "z"), ("cash_risk", "critical", "z"),
        ("goal_risk", "medium", "a")]]
    generated.recommendations = rows
    monkeypatch.setattr("app.services.finance.coaching_feedback.financial_coaching", lambda *a, **kw: generated.model_copy(deep=True))
    result = action_plan(db, users[0].id)
    expected = [rows[i].id for i in (7, 6, 5, 4, 8)]
    assert [a.id for a in result.actions] == expected
    assert result.active_count == MAX_ACTIVE_ACTIONS and LIMIT_NOTE in result.limitations
    assert result.completed_count == 0
    assert [a.rank for a in result.actions] == [1, 2, 3, 4, 5]
    generated.recommendations = list(reversed(rows))
    assert action_plan(db, users[0].id) == result
    medium = action_plan(db, users[0].id, priority="medium")
    assert [a.id for a in medium.actions] == [rows[i].id for i in (5, 4, 8, 1, 3)]
    generated.recommendations = [synthetic("cash_risk", "critical", str(n)) for n in range(7)] + rows
    result = action_plan(db, users[0].id)
    assert result.active_count == 8 and all(a.priority == "critical" for a in result.actions)
