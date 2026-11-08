"""Synthetic regression coverage for mailbox authority and password recovery."""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth
from app.core.database import Base, get_db
from app.main import app
from app.models import User
from app.models.email_verification import EmailVerificationToken
from app.services.notifications.dispatcher import _prepare_message, get_or_create_user_preferences
from app.services.notifications.digest_engine import generate_daily_digest_for_user
from app.services.notifications.eligibility import evaluate_eligibility
from app.services.notifications.email_sender import TestEmailSender


@pytest.fixture
def account():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    def get_test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = get_test_db
    auth._failed_attempts.clear()
    TestEmailSender.clear()
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.pop(get_db, None)
    auth._failed_attempts.clear()
    TestEmailSender.clear()
    engine.dispose()


def register(client):
    result = client.post("/register", json={"email": "owner@example.com", "password": "correct-password-for-tests"})
    assert result.status_code == 200
    return {"Authorization": "Bearer " + result.json()["access_token"]}


def captured_token():
    message = TestEmailSender.get_sent_messages()[-1]
    return re.search(r"#token=([A-Za-z0-9_-]+)", message.body_text).group(1)


def test_unknown_login_is_401(account):
    client, _ = account
    assert client.post("/login", json={"email": "missing@example.com", "password": "wrong"}).status_code == 401


def test_mailbox_proof_is_one_use_and_not_returned(account):
    client, factory = account
    headers = register(client)
    path = "/finance/notification-preferences"
    assert client.put(path, headers=headers, json={"email_enabled": True, "email_consent": True}).status_code == 403
    result = client.post("/auth/email-verification/request", headers=headers)
    assert result.status_code == 202
    token = captured_token()
    assert token not in result.text
    with factory() as db:
        record = db.query(EmailVerificationToken).one()
        assert record.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert record.token_hash != token
    assert client.post("/auth/email-verification/confirm", json={"token": token}).status_code == 200
    assert client.post("/auth/email-verification/confirm", json={"token": token}).status_code == 400
    assert client.put(path, headers=headers, json={"email_enabled": True, "email_consent": True}).status_code == 200


def test_legacy_recovery_invalidates_existing_tokens(account, monkeypatch):
    client, factory = account
    monkeypatch.setattr(auth.settings, "PEPPER", "P" * 72)
    with factory() as db:
        user = User(email="legacy@example.com", hashed_password=bcrypt.hashpw(b"P" * 72, bcrypt.gensalt()).decode())
        db.add(user)
        db.commit()
        identity = {"sub": user.email, "user_id": user.id, "ver": 0}
    old_access = auth.create_access_token(identity)
    old_refresh = auth.create_refresh_token(identity)
    assert client.post("/login", json={"email": "legacy@example.com", "password": "unrelated"}).status_code == 401
    assert client.post("/auth/password-reset/request", json={"email": "legacy@example.com"}).status_code == 202
    token = captured_token()
    assert client.post("/auth/email-verification/confirm", json={"token": token}).status_code == 400
    assert client.post("/auth/password-reset/confirm", json={"token": token, "password": "replacement-password"}).status_code == 200
    assert client.post("/auth/password-reset/confirm", json={"token": token, "password": "another-password"}).status_code == 400
    assert client.get("/me", headers={"Authorization": "Bearer " + old_access}).status_code == 401
    assert client.post("/refresh", data={"refresh_token": old_refresh}).status_code == 401
    result = client.post("/login", json={"email": "legacy@example.com", "password": "replacement-password"})
    assert result.status_code == 200
    assert client.get("/me", headers={"Authorization": "Bearer " + result.json()["access_token"]}).status_code == 200


def test_expired_mailbox_token_rejected(account):
    client, factory = account
    headers = register(client)
    client.post("/auth/email-verification/request", headers=headers)
    token = captured_token()
    with factory() as db:
        db.query(EmailVerificationToken).one().expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.post("/auth/email-verification/confirm", json={"token": token}).status_code == 400


def test_preexisting_email_consent_cannot_bypass_proof(account):
    client, factory = account
    register(client)
    with factory() as db:
        user = db.query(User).one()
        pref = get_or_create_user_preferences(db, user.id)
        pref.email_enabled = pref.email_consent = pref.daily_digest_enabled = True
        db.commit()
        assert not evaluate_eligibility(pref, channel="email", alert_severity="critical", notification_event="ALERT_CREATED").is_eligible
        assert not evaluate_eligibility(pref, user=user, channel="email", alert_severity="critical", notification_event="ALERT_CREATED").is_eligible
        delivery = SimpleNamespace(channel="email", user_id=user.id)
        assert _prepare_message(db, delivery, datetime.now(timezone.utc))[1] == "SUPPRESSED"
        assert generate_daily_digest_for_user(db, user.id, force=True)[0] is None
    assert TestEmailSender.get_sent_messages() == []
