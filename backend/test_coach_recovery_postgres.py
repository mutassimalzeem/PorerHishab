"""Actual PostgreSQL uniqueness, concurrent claims, fencing and legacy migration."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import inspect, text

from app.models import User
from app.models.financial_coach import CoachConversation, CoachMessage, CoachTurn
from app.schemas.financial_coach import CoachRequest, CoachResponse, CoachIntent
from app.services.finance.financial_coach_persistence import claim_turn, complete_turn, fail_turn, get_turn
from backend.test_obligation_reconciliation import store  # noqa: F401


def test_concurrent_receipts_and_expired_claims(store):
    factory, _ = store
    with factory() as db:
        user = User(email=f"{uuid4().hex}@example.com", hashed_password="test")
        db.add(user); db.commit(); uid = user.id
    req = CoachRequest(request_id=uuid4(), message="How much did I spend?")

    def race():
        barrier = Barrier(2)
        def attempt():
            with factory() as db:
                barrier.wait(timeout=15)
                try:
                    turn, token = claim_turn(db, uid, req, "en")
                    return token
                except HTTPException as exc:
                    db.rollback()
                    assert exc.status_code == 409
                    return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt) for _ in range(2)]
            return [f.result(timeout=30) for f in futures]

    tokens = race()
    assert sum(token is not None for token in tokens) == 1
    old_token = next(t for t in tokens if t)
    with factory() as db:
        assert db.query(CoachConversation).filter_by(user_id=uid).count() == 1
        assert db.query(CoachMessage).filter_by(user_id=uid).count() == 1
        turn = get_turn(db, uid, req.request_id)
        turn.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    claimed = race()
    assert sum(token is not None for token in claimed) == 1
    token = next(t for t in claimed if t)
    with factory() as db:
        try:
            complete_turn(db, uid, str(req.request_id), old_token, CoachResponse(intent=CoachIntent.SPENDING_ANALYSIS, answer="Stale worker"))
            raise AssertionError("Expired worker committed")
        except HTTPException as exc:
            assert exc.status_code == 409
        result = complete_turn(db, uid, str(req.request_id), token, CoachResponse(intent=CoachIntent.SPENDING_ANALYSIS, answer="Current worker"))
        replay, none = claim_turn(db, uid, req, "en")
        assert none is None and replay.response_json == result.model_dump(mode="json")
        assert db.query(CoachMessage).filter_by(user_id=uid, role="assistant").count() == 1


def test_recovery_migration_preserves_legacy_messages(store):
    factory, engine = store
    config = Config("alembic.ini")
    command.downgrade(config, "f15s00000002")
    with engine.begin() as db:
        uid = db.execute(text("INSERT INTO users (email, hashed_password, created_at, updated_at) VALUES (:email, 'test', now(), now()) RETURNING id"), {"email": uuid4().hex + "@example.com"}).scalar_one()
        db.execute(text("INSERT INTO coach_conversations (id, user_id, title, created_at, updated_at) VALUES ('legacy-recovery', :uid, 'Legacy', now(), now())"), {"uid": uid})
        db.execute(text("INSERT INTO coach_messages (conversation_id, user_id, role, content, created_at) VALUES ('legacy-recovery', :uid, 'user', 'Old question', now())"), {"uid": uid})
    command.upgrade(config, "head")
    assert "coach_turns" in inspect(engine).get_table_names()
    with factory() as db:
        legacy = db.query(CoachMessage).filter_by(conversation_id="legacy-recovery").one()
        assert legacy.content == "Old question" and legacy.request_id is None
        req = CoachRequest(request_id=uuid4(), message="New question", conversation_id="legacy-recovery")
        turn, token = claim_turn(db, uid, req, "en")
        fail_turn(db, uid, turn.request_id, token)
    command.downgrade(config, "f15s00000002")
    with engine.connect() as db:
        assert db.execute(text("SELECT content FROM coach_messages WHERE conversation_id='legacy-recovery' ORDER BY id LIMIT 1")).scalar_one() == "Old question"
    command.upgrade(config, "head")
