"""AI-15G API lifecycle, owner isolation and deterministic visibility."""
from datetime import timedelta
from decimal import Decimal
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models.coaching_feedback import CoachingFeedback
from app.schemas.coaching import CoachingFeedbackInput
from app.services.finance.coaching import financial_coaching
from app.services.finance.coaching_feedback import submit, restore, visible_coaching
from backend.test_financial_runway import data, plan, AS_OF  # noqa: F401


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr("app.services.finance.coaching.today_dhaka", lambda: AS_OF)
    monkeypatch.setattr("app.services.intelligence.periods.today_dhaka", lambda: AS_OF)


@pytest.fixture
def client(data):
    db, users, _ = data
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: users[0]
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def seed(data):
    db, users, _ = data
    plan(db, users[0])
    return financial_coaching(db, users[0].id).recommendations[0].id


@pytest.mark.parametrize("status", ["dismissed", "acted_on", "not_relevant", "snoozed"])
def test_authenticated_lifecycle(data, client, status):
    db, users, _ = data
    key = seed(data)
    before = financial_coaching(db, users[0].id).model_dump()
    body = {"status": status}
    if status == "snoozed":
        body["snoozed_until"] = str(AS_OF + timedelta(days=3))
    response = client.put(f"/finance/coaching/{key}/feedback", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["is_current"] and response.json()["is_hidden"]
    assert response.json()["created_at"] and response.json()["updated_at"]
    assert key not in {r["id"] for r in client.get("/finance/coaching").json()["recommendations"]}
    assert client.get("/finance/coaching/feedback").json()[0]["status"] == status
    created = response.json()["created_at"]
    response = client.put(f"/finance/coaching/{key}/feedback", json={"status": "dismissed"})
    assert response.status_code == 200 and response.json()["created_at"] == created
    assert response.json()["snoozed_until"] is None
    assert db.query(CoachingFeedback).count() == 1
    assert client.delete(f"/finance/coaching/{key}/feedback").status_code == 204
    assert key in {r["id"] for r in client.get("/finance/coaching").json()["recommendations"]}
    assert client.get("/finance/coaching/feedback").json() == []
    assert financial_coaching(db, users[0].id).model_dump() == before


@pytest.mark.parametrize("body", [
    {"status":"unknown"}, {"status":"snoozed"},
    {"status":"snoozed", "snoozed_until":"2026-11-01"},
    {"status":"snoozed", "snoozed_until":"2026-10-31"},
    {"status":"snoozed", "snoozed_until":"2027-02-01"},
    {"status":"snoozed", "snoozed_until":"bad"},
    {"status":"dismissed", "snoozed_until":"2026-11-03"},
    {"status":"dismissed", "user_id":2}, {"status":"acted_on", "amount":100},
])
def test_invalid_input(data, client, body):
    key = seed(data)
    assert client.put(f"/finance/coaching/{key}/feedback", json=body).status_code == 422
    assert data[0].query(CoachingFeedback).count() == 0


def test_invalid_and_expired_ids(data, client, monkeypatch):
    key = seed(data)
    assert client.put("/finance/coaching/invented/feedback", json={"status":"dismissed"}).status_code == 404
    db, users, _ = data
    generated = financial_coaching(db, users[0].id)
    generated.recommendations[0].valid_until = AS_OF - timedelta(days=1)
    monkeypatch.setattr("app.services.finance.coaching_feedback.financial_coaching", lambda *a, **k: generated)
    assert client.put(f"/finance/coaching/{key}/feedback", json={"status":"dismissed"}).status_code == 404


def test_owner_isolation_and_same_id(data, client):
    db, users, _ = data
    key = seed(data)
    assert client.put(f"/finance/coaching/{key}/feedback", json={"status":"dismissed"}).status_code == 200
    app.dependency_overrides[get_current_user] = lambda: users[1]
    assert client.get("/finance/coaching/feedback").json() == []
    assert client.put(f"/finance/coaching/{key}/feedback", json={"status":"acted_on"}).status_code == 404
    client.delete(f"/finance/coaching/{key}/feedback")
    assert db.query(CoachingFeedback).count() == 1
    # Cash-risk identifiers intentionally match across users for the same horizon.
    data[2].opening_balance = Decimal("0")
    db.commit()
    plan(db, users[1], amount="500")
    from app.models.account import Account
    db.add(Account(user_id=users[1].id, name="Cash", currency="BDT", opening_balance=Decimal("0"), opening_balance_date=AS_OF))
    db.commit()
    for user in users:
        risk = next(r for r in financial_coaching(db, user.id).recommendations if r.type == "cash_risk")
        submit(db, user.id, risk.id, CoachingFeedbackInput(status="dismissed"))
    rows = db.query(CoachingFeedback).filter(CoachingFeedback.recommendation_id.like("cash_risk:%")).all()
    assert len(rows) == 2 and rows[0].recommendation_id == rows[1].recommendation_id


def test_expiry_and_changed_facts_resurface(data):
    db, users, account = data
    key = seed(data)
    submit(db, users[0].id, key, CoachingFeedbackInput(status="snoozed", snoozed_until=AS_OF + timedelta(days=1)))
    row = db.query(CoachingFeedback).one()
    row.snoozed_until = AS_OF
    db.commit()
    result = visible_coaching(db, users[0].id)
    assert key in {r.id for r in result.recommendations}
    assert result.feedback[0].is_current and not result.feedback[0].is_hidden
    submit(db, users[0].id, key, CoachingFeedbackInput(status="dismissed"))
    account.opening_balance = Decimal("100")
    db.commit()
    result = visible_coaching(db, users[0].id)
    assert key in {r.id for r in result.recommendations}
    assert not result.feedback[0].is_current


def test_disappeared_recommendation_is_history_only(data):
    db, users, _ = data
    item = plan(db, users[0])
    key = financial_coaching(db, users[0].id).recommendations[0].id
    submit(db, users[0].id, key, CoachingFeedbackInput(status="dismissed"))
    item.status = "paid"
    db.commit()
    result = visible_coaching(db, users[0].id)
    assert not result.feedback[0].is_current
    with pytest.raises(HTTPException) as error:
        submit(db, users[0].id, key, CoachingFeedbackInput(status="acted_on"))
    assert error.value.status_code == 404
    restore(db, users[0].id, key)
    assert not visible_coaching(db, users[0].id).recommendations


def test_financial_tables_never_written(data):
    db, users, _ = data
    key = seed(data)
    writes = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        for status in ("dismissed", "acted_on", "not_relevant"):
            submit(db, users[0].id, key, CoachingFeedbackInput(status=status))
        restore(db, users[0].id, key)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert len(writes) == 4 and all("coaching_feedback" in sql for sql in writes)


def test_authentication_required():
    with TestClient(app) as client:
        for method, path in [("get", "/finance/coaching/feedback"), ("put", "/finance/coaching/x/feedback"), ("delete", "/finance/coaching/x/feedback")]:
            response = getattr(client, method)(path, **({"json":{"status":"dismissed"}} if method == "put" else {}))
            assert response.status_code == 401


def test_snooze_boundary_and_date_rollover(data):
    db, users, _ = data
    plan(db, users[0], due=AS_OF + timedelta(days=5))
    generated = financial_coaching(db, users[0].id)
    key = next(row.id for row in generated.recommendations if row.type == "upcoming_obligations")
    payload = CoachingFeedbackInput(status="snoozed", snoozed_until=AS_OF + timedelta(days=90))
    submit(db, users[0].id, key, payload)
    assert key not in {row.id for row in visible_coaching(db, users[0].id, as_of=AS_OF + timedelta(days=1)).recommendations}
    submit(db, users[0].id, key, CoachingFeedbackInput(status="snoozed", snoozed_until=AS_OF + timedelta(days=1)))
    assert key in {row.id for row in visible_coaching(db, users[0].id, as_of=AS_OF + timedelta(days=1)).recommendations}
    with pytest.raises(ValueError):
        CoachingFeedbackInput(status="snoozed", snoozed_until=AS_OF + timedelta(days=91))


def test_custom_threshold_scope(data, client):
    db, users, _ = data
    generated = client.get("/finance/coaching?safety_threshold=30000").json()
    risk = next(row for row in generated["recommendations"] if row["type"] == "cash_risk")
    path = f"/finance/coaching/{risk['id']}/feedback"
    assert client.put(path, json={"status":"dismissed"}).status_code == 404
    assert client.put(path + "?safety_threshold=30000", json={"status":"dismissed"}).status_code == 200
    assert not client.get("/finance/coaching?safety_threshold=30000").json()["recommendations"]
    assert client.get("/finance/coaching").json()["feedback"][0]["is_current"] is False


def test_large_obligation_identity_is_bounded_and_stable(data):
    from app.models import ScheduledCashflowItem
    db, users, _ = data
    db.add_all([ScheduledCashflowItem(user_id=users[0].id, title=f"Bill {n}", kind="expense", amount=100, due_date=AS_OF, status="scheduled") for n in range(150)])
    db.commit()
    generated = financial_coaching(db, users[0].id)
    item = next(row for row in generated.recommendations if row.type == "upcoming_obligations")
    assert len(item.source_id) > 300 and len(item.id) < 100
    assert len(item.evidence.obligations) == 150 and item.amount == 15000
    assert item.id == next(row.id for row in financial_coaching(db, users[0].id).recommendations if row.type == item.type)
    submit(db, users[0].id, item.id, CoachingFeedbackInput(status="dismissed"))
    assert item.id not in {row.id for row in visible_coaching(db, users[0].id).recommendations}


def test_new_risk_horizon_is_not_hidden(data):
    db, users, account = data
    account.opening_balance = Decimal("0")
    db.commit()
    plan(db, users[0], due=AS_OF + timedelta(days=3))
    risk = next(row for row in financial_coaching(db, users[0].id).recommendations if row.type == "cash_risk")
    submit(db, users[0].id, risk.id, CoachingFeedbackInput(status="dismissed"))
    later = visible_coaching(db, users[0].id, as_of=AS_OF + timedelta(days=1))
    new_risk = next(row for row in later.recommendations if row.type == "cash_risk")
    assert new_risk.id != risk.id and not later.feedback[0].is_current
