"""Receipts, partial commits, replay, fencing and bounded owner-scoped history."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.financial_coach import CoachTurn, CoachMessage, CoachConversation
from app.schemas.financial_coach import CoachRequest, CoachResponse, CoachIntent
from app.services.finance.financial_coach_persistence import (
    claim_turn, complete_turn, fail_turn, get_turn, turn_view,
    get_recent_history_context, get_conversation_messages, delete_conversation,
)
from test_financial_coach_persistence import db_session, users  # noqa: F401
from test_financial_coach_api import test_setup  # noqa: F401


@pytest.fixture(autouse=True)
def offline_recovery(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", False)
    monkeypatch.setattr(settings, "OPENAI_KEY", None)


def payload(**kwargs):
    return CoachRequest(message="Where did my money go?", request_id=uuid4(), **kwargs)


def answer():
    return CoachResponse(intent=CoachIntent.SPENDING_ANALYSIS, answer="Only recorded evidence is available.")


def test_receipt_replay_and_separate_identical_turns(db_session, users):
    db, uid = db_session, users[0].id
    req = payload()
    turn, token = claim_turn(db, uid, req, "en")
    assert len(get_conversation_messages(db, uid, turn.conversation_id)) == 1
    with pytest.raises(HTTPException) as err:
        claim_turn(db, uid, req, "en")
    assert err.value.status_code == 409
    db.rollback()
    completed = complete_turn(db, uid, str(req.request_id), token, answer()).model_dump(mode="json")
    replay, no_token = claim_turn(db, uid, req, "en")
    assert no_token is None and replay.response_json == completed
    second, token2 = claim_turn(db, uid, payload(conversation_id=turn.conversation_id), "en")
    complete_turn(db, uid, second.request_id, token2, answer())
    assert db.query(CoachMessage).count() == 4
    assert db.query(CoachTurn).count() == 2


def test_failure_retries_same_user_message_and_updates_activity(db_session, users):
    db, uid = db_session, users[0].id
    req = payload()
    turn, token = claim_turn(db, uid, req, "en")
    failed_at = turn.updated_at
    fail_turn(db, uid, turn.request_id, token)
    assert turn_view(db, uid, get_turn(db, uid, turn.request_id)).retry_safe
    retry, token2 = claim_turn(db, uid, req, "en")
    assert token2 != token
    assert retry.updated_at >= failed_at
    assert get_recent_history_context(db, uid, retry.conversation_id) == []
    complete_turn(db, uid, retry.request_id, token2, answer())
    assert [m.role for m in get_conversation_messages(db, uid, retry.conversation_id)] == ["user", "assistant"]


def test_expired_worker_cannot_publish_after_reclaim(db_session, users):
    db, uid = db_session, users[0].id
    req = payload()
    turn, token = claim_turn(db, uid, req, "en")
    turn.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert turn_view(db, uid, turn).status == "interrupted"
    reclaimed, new_token = claim_turn(db, uid, req, "en")
    with pytest.raises(HTTPException):
        complete_turn(db, uid, turn.request_id, token, answer())
    complete_turn(db, uid, reclaimed.request_id, new_token, answer())
    fail_turn(db, uid, turn.request_id, token)
    assert get_turn(db, uid, turn.request_id).state == "completed"
    assert db.query(CoachMessage).filter_by(role="assistant").count() == 1


@pytest.mark.parametrize("change", ["message", "language", "conversation_id", "schedules_confirmed"])
def test_key_context_conflicts(db_session, users, change):
    db, uid = db_session, users[0].id
    req = payload()
    turn, token = claim_turn(db, uid, req, "en")
    complete_turn(db, uid, turn.request_id, token, answer())
    changed = req.model_copy(update={change: {"message": "Different question", "conversation_id": "other",
                                             "schedules_confirmed": True}.get(change)})
    with pytest.raises(HTTPException) as err:
        claim_turn(db, uid, req if change == "language" else changed, "bn" if change == "language" else "en")
    assert err.value.status_code == 409


def test_owner_scoped_keys_and_delete(db_session, users):
    db, uid = db_session, users[0].id
    req = payload()
    turn, token = claim_turn(db, uid, req, "en")
    assert get_turn(db, users[1].id, turn.request_id) is None
    with pytest.raises(HTTPException) as err:
        claim_turn(db, users[1].id, req.model_copy(update={"conversation_id": turn.conversation_id}), "en")
    assert err.value.status_code == 404
    db.rollback()
    other, _ = claim_turn(db, users[1].id, req, "en")
    assert other.conversation_id != turn.conversation_id
    assert delete_conversation(db, uid, turn.conversation_id)
    assert get_turn(db, uid, turn.request_id) is None
    assert db.query(CoachMessage).filter_by(user_id=uid).count() == 0


def test_older_failed_turn_cannot_be_retried_after_new_question(db_session, users):
    db, uid = db_session, users[0].id
    req = payload()
    turn, token = claim_turn(db, uid, req, "en")
    fail_turn(db, uid, turn.request_id, token)
    new, token2 = claim_turn(db, uid, payload(conversation_id=turn.conversation_id), "en")
    complete_turn(db, uid, new.request_id, token2, answer())
    assert not turn_view(db, uid, get_turn(db, uid, turn.request_id)).retry_safe
    with pytest.raises(HTTPException):
        claim_turn(db, uid, req, "en")


def test_latest_history_and_cursor_include_legacy_records(db_session, users):
    db, uid = db_session, users[0].id
    req = payload()
    turn, token = claim_turn(db, uid, req, "en")
    complete_turn(db, uid, turn.request_id, token, answer())
    for i in range(220):
        db.add(CoachMessage(user_id=uid, conversation_id=turn.conversation_id,
                            role="user" if i % 2 == 0 else "assistant", content=f"legacy {i}"))
    db.commit()
    newest = get_conversation_messages(db, uid, turn.conversation_id, limit=100)
    assert newest[-1].content == "legacy 219"
    assert [m.id for m in newest] == sorted(m.id for m in newest)
    older = get_conversation_messages(db, uid, turn.conversation_id, limit=200, before_id=newest[0].id)
    assert len(older) == 122
    assert len(get_recent_history_context(db, uid, turn.conversation_id, limit=1000)) == 20


def test_api_lost_response_replays_without_generation(test_setup, monkeypatch):
    import app.api.financial_coach as endpoint
    client, headers = test_setup["client"], test_setup["headers1"]
    req = {"message": "Where did my money go?", "request_id": str(uuid4())}
    first = client.post("/coach/ask", headers=headers, json=req)
    assert first.status_code == 200, first.text
    def forbidden(*args, **kwargs):
        pytest.fail("A completed turn must not assemble fresh evidence or regenerate")
    monkeypatch.setattr(endpoint, "assemble_financial_evidence", forbidden)
    replay = client.post("/coach/ask", headers=headers, json=req)
    assert replay.json() == first.json()
    status = client.get(f"/coach/requests/{req['request_id']}", headers=headers)
    assert status.json()["response"] == first.json()
    assert client.get(f"/coach/requests/{req['request_id']}").status_code == 401
    assert client.get(f"/coach/requests/{req['request_id']}", headers=test_setup["headers2"]).status_code == 404
    assert client.post("/coach/ask", headers=test_setup["headers2"],
                       json={**req, "conversation_id": first.json()["conversation_id"]}).status_code == 404


def test_api_failed_generation_recovers_with_fresh_evidence(test_setup, monkeypatch):
    import app.api.financial_coach as endpoint
    from app.models import Account, Transaction
    client, headers, db = test_setup["client"], test_setup["headers1"], test_setup["session"]
    before = [(a.id, a.current_balance) for a in db.query(Account)]
    tx_before = db.query(Transaction).count()
    req = {"message": "Where did my money go?", "request_id": str(uuid4())}
    real = endpoint.assemble_financial_evidence
    def broken(*args, **kwargs):
        raise RuntimeError("provider-secret private financial details")
    monkeypatch.setattr(endpoint, "assemble_financial_evidence", broken)
    failed = client.post("/coach/ask", headers=headers, json=req)
    assert failed.status_code == 500
    assert "provider-secret" not in failed.text
    status = client.get(f"/coach/requests/{req['request_id']}", headers=headers).json()
    assert status["status"] == "failed" and status["retry_safe"]
    calls = []
    def fresh(*args, **kwargs):
        calls.append(True)
        return real(*args, **kwargs)
    monkeypatch.setattr(endpoint, "assemble_financial_evidence", fresh)
    retried = client.post("/coach/ask", headers=headers, json=req)
    assert retried.status_code == 200, retried.text
    assert len(calls) == 1
    detail = client.get(f"/coach/conversations/{status['conversation_id']}", headers=headers).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["turn_status"] == "completed"
    assert [(a.id, a.current_balance) for a in db.query(Account)] == before
    assert db.query(Transaction).count() == tx_before


def test_api_cursor_and_more_than_ten_conversations(test_setup):
    db, uid = test_setup["session"], test_setup["u1"].id
    for i in range(12):
        db.add(CoachConversation(user_id=uid, title=f"History {i}"))
    db.commit()
    conv = db.query(CoachConversation).first()
    for i in range(205):
        db.add(CoachMessage(user_id=uid, conversation_id=conv.id, role="user", content=f"message {i}"))
    db.commit()
    client, headers = test_setup["client"], test_setup["headers1"]
    newest = client.get(f"/coach/conversations/{conv.id}", headers=headers).json()
    assert newest["messages"][-1]["content"] == "message 204"
    assert newest["has_more"]
    previous = client.get(f"/coach/conversations/{conv.id}?before_id={newest['next_before_id']}", headers=headers).json()
    assert previous["messages"][-1]["id"] < newest["messages"][0]["id"]
    assert client.get("/coach/conversations?limit=10&offset=10", headers=headers).json()["total"] == 12
    assert len(client.get("/coach/conversations?limit=10&offset=10", headers=headers).json()["items"]) == 2


def test_api_error_after_completion_cannot_mark_saved_answer_failed(test_setup, monkeypatch):
    import app.api.financial_coach as endpoint
    real = endpoint.complete_turn
    def save_then_lose_response(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("Lost socket after committed assistant")
    monkeypatch.setattr(endpoint, "complete_turn", save_then_lose_response)
    client, headers = test_setup["client"], test_setup["headers1"]
    req = {"request_id": str(uuid4()), "message": "What bills are coming up?"}
    failure = client.post("/coach/ask", headers=headers, json=req)
    assert failure.status_code == 500 and "Lost socket" not in failure.text
    state = client.get(f"/coach/requests/{req['request_id']}", headers=headers).json()
    assert state["status"] == "completed" and state["response"]
    replay = client.post("/coach/ask", headers=headers, json=req)
    assert replay.status_code == 200 and replay.json() == state["response"]
    assert test_setup["session"].query(CoachMessage).filter_by(role="assistant").count() == 1


def test_failed_initial_receipt_does_not_leave_orphan_conversation(test_setup):
    from sqlalchemy import event
    db, client, headers = test_setup["session"], test_setup["client"], test_setup["headers1"]
    engine = db.get_bind()
    def fail_user_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO COACH_MESSAGES"):
            raise RuntimeError("Interrupted receipt")
    event.listen(engine, "before_cursor_execute", fail_user_insert)
    try:
        response = client.post("/coach/ask", headers=headers,
                               json={"message": "What bills are coming up?", "request_id": str(uuid4())})
    finally:
        event.remove(engine, "before_cursor_execute", fail_user_insert)
    assert response.status_code == 500
    assert db.query(CoachConversation).count() == db.query(CoachTurn).count() == db.query(CoachMessage).count() == 0


def test_generation_does_not_hold_a_database_transaction(test_setup, monkeypatch):
    import app.api.financial_coach as endpoint
    captured = []
    generated = []
    real = endpoint.assemble_financial_evidence
    def capture(*args, **kwargs):
        captured.append(kwargs["db"])
        return real(*args, **kwargs)
    def generate(self, package, **kwargs):
        assert captured and not captured[-1].in_transaction()
        generated.append(True)
        return CoachResponse(intent=package.intent, answer="Review the recorded evidence.")
    monkeypatch.setattr(endpoint, "assemble_financial_evidence", capture)
    monkeypatch.setattr(endpoint.FinancialCoachGenerator, "generate_response", generate)
    result = test_setup["client"].post("/coach/ask", headers=test_setup["headers1"],
                                        json={"message": "Where did my money go?", "request_id": str(uuid4())})
    assert result.status_code == 200, result.text
    assert generated == [True]
