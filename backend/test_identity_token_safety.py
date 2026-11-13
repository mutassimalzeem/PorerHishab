"""Synthetic identity router/token fixtures; no financial app or real SMTP."""
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth, email_verification as api
from app.core.database import Base, get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.models.email_verification import EmailVerificationToken
from app.services.email_verification import create_verification_token, consume_verification_token
from app.services.notifications import email_sender as delivery


@pytest.fixture
def mailbox():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(User(email="synthetic@example.com", hashed_password="unused-in-router-fixture"))
        db.commit()
    def database():
        with factory() as db:
            yield db
    def owner():
        with factory() as db:
            return db.query(User).one()
    application = FastAPI()
    application.include_router(api.router)
    application.dependency_overrides[get_db] = database
    # This fixture verifies the identity router, not authentication middleware.
    application.dependency_overrides[get_current_user] = owner
    auth._failed_attempts.clear()
    with TestClient(application) as client:
        yield client, factory
    auth._failed_attempts.clear()
    engine.dispose()


def raw_token(message):
    return re.search(r"#token=([A-Za-z0-9_-]+)", message.body_text).group(1)


def request(client, purpose):
    if purpose == "verify_email":
        return client.post("/auth/email-verification/request")
    return client.post("/auth/password-reset/request", json={"email": "synthetic@example.com"})


def confirm(client, purpose, raw):
    if purpose == "verify_email":
        return client.post("/auth/email-verification/confirm", json={"token": raw})
    return client.post("/auth/password-reset/confirm", json={"token": raw, "password": "synthetic-new-password"})


@pytest.mark.parametrize("purpose", ["verify_email", "reset_password"])
def test_failed_smtp_token_unusable_throttled_retry_and_one_use(mailbox, monkeypatch, caplog, purpose):
    client, factory = mailbox
    caplog.set_level(logging.DEBUG)
    for name, value in {"APP_ENV": "production", "SECURITY_EMAIL_DELIVERY_ENABLED": True,
                        "SECURITY_EMAIL_BACKEND": "smtp", "NOTIFICATION_DELIVERY_ENABLED": False,
                        "SMTP_HOST": "smtp.example.invalid", "SMTP_USERNAME": "synthetic-user",
                        "SMTP_PASSWORD": "SYNTHETIC_SMTP_PASSWORD"}.items():
        monkeypatch.setattr(api.settings, name, value)
    captured = []
    original = delivery.SmtpEmailSender.send
    def capture(self, message):
        captured.append(raw_token(message))
        return original(self, message)
    monkeypatch.setattr(delivery.SmtpEmailSender, "send", capture)
    with patch.object(delivery.smtplib, "SMTP", side_effect=OSError("SYNTHETIC_SMTP_DIAGNOSTIC")) as smtp:
        failed = request(client, purpose)
        assert failed.status_code == 202
        assert request(client, purpose).json() == failed.json()
        assert smtp.call_count == 1
        rejected = confirm(client, purpose, captured[0])
        assert rejected.status_code == 400
        with factory() as db:
            row = db.query(EmailVerificationToken).one()
            assert row.token_hash == hashlib.sha256(captured[0].encode()).hexdigest()
            assert row.used_at is not None
            assert not consume_verification_token(db, captured[0], purpose, "synthetic-new-password")
            row.created_at = datetime.now(timezone.utc) - timedelta(seconds=61)
            db.commit()
        smtp.side_effect = None
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        assert request(client, purpose).status_code == 202
        assert smtp.call_count == 2 and len(captured) == 2 and captured[0] != captured[1]
        wrong_purpose = "reset_password" if purpose == "verify_email" else "verify_email"
        assert confirm(client, wrong_purpose, captured[1]).status_code == 400
        assert confirm(client, purpose, captured[1]).status_code == 200
        assert confirm(client, purpose, captured[1]).status_code == 400
    with factory() as db:
        user = db.query(User).one()
        assert user.email_verified
        if purpose == "reset_password":
            assert user.token_version == 1
            assert auth.verify_password("synthetic-new-password", user.hashed_password)
    for secret in captured + ["SYNTHETIC_SMTP_PASSWORD", "SYNTHETIC_SMTP_DIAGNOSTIC"]:
        assert secret not in caplog.text
        assert secret not in failed.text and secret not in rejected.text


def test_smtp_failure_keeps_known_unknown_account_responses_equal(mailbox, monkeypatch):
    client, _ = mailbox
    monkeypatch.setattr(api.settings, "SECURITY_EMAIL_BACKEND", "smtp")
    with patch.object(delivery.smtplib, "SMTP", side_effect=OSError("synthetic failure")):
        known = request(client, "reset_password")
        unknown = client.post("/auth/password-reset/request", json={"email": "missing@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


@pytest.mark.parametrize("purpose", ["verify_email", "reset_password"])
def test_late_failed_delivery_cannot_invalidate_replacement_or_other_purpose(mailbox, monkeypatch, purpose):
    _, factory = mailbox
    captured = {}
    other_purpose = "reset_password" if purpose == "verify_email" else "verify_email"
    class OverlappingDelivery:
        def send(self, message):
            captured["old"] = raw_token(message)
            # Deterministic overlap: the older SMTP call is still in flight while
            # a newer eligible request replaces its challenge in another session.
            with factory() as concurrent:
                old = concurrent.query(EmailVerificationToken).filter_by(purpose=purpose).one()
                old.created_at = datetime.now(timezone.utc) - timedelta(seconds=61)
                concurrent.commit()
                owner = concurrent.query(User).one()
                captured["new"] = create_verification_token(concurrent, owner, purpose)
                captured["other"] = create_verification_token(concurrent, owner, other_purpose)
            return delivery.EmailSendResult(False, "smtp", "synthetic old failure")
    monkeypatch.setattr(api, "get_identity_email_sender", lambda: OverlappingDelivery())
    with factory() as db:
        api.send_challenge(db, db.query(User).one(), purpose)
    with factory() as db:
        rows = db.query(EmailVerificationToken).all()
        assert len(rows) == 2 and all(row.used_at is None for row in rows)
        assert not consume_verification_token(db, captured["old"], purpose, "synthetic-new-password")
        assert not consume_verification_token(db, captured["new"], other_purpose, "synthetic-new-password")
        assert consume_verification_token(db, captured["new"], purpose, "synthetic-new-password")
        assert consume_verification_token(db, captured["other"], other_purpose, "synthetic-new-password")


def test_expiry_and_separate_owner_tokens(mailbox):
    _, factory = mailbox
    with factory() as db:
        owner = db.query(User).one()
        raw = create_verification_token(db, owner, "verify_email")
        row = db.query(EmailVerificationToken).one()
        expiry = row.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        assert timedelta(minutes=29) < expiry - datetime.now(timezone.utc) <= timedelta(minutes=30)
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.add(User(email="second@example.com", hashed_password="unused"))
        db.commit()
        second = db.query(User).filter_by(email="second@example.com").one()
        second_raw = create_verification_token(db, second, "verify_email")
        assert not consume_verification_token(db, raw, "verify_email")
        assert consume_verification_token(db, second_raw, "verify_email")
