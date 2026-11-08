"""Actual PostgreSQL recovery, retry, concurrency, API isolation and provider semantics."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
import smtplib

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.api.auth import create_access_token
from app.core.database import get_db
from app.main import app
from app.models import User
from app.models.financial_alert import FinancialAlert
from app.models.notification_delivery import NotificationDelivery
from app.services.notifications import dispatcher as d
from app.services.notifications.email_sender import EmailSendResult, EmailMessage, SmtpEmailSender, TestEmailSender
from backend.test_obligation_reconciliation import store  # noqa: F401


@pytest.fixture
def delivery(store):
    factory, _ = store
    with factory() as db:
        user = User(email=uuid4().hex + "@example.com", hashed_password="test", email_verified=True)
        db.add(user); db.flush()
        alert = FinancialAlert(user_id=user.id, alert_key=uuid4().hex,
            alert_type="cash_shortfall", severity="critical", title="Private title",
            title_key="test", message="Private financial data", message_key="test",
            recommended_action="Review", status="active")
        db.add(alert); db.flush()
        pref = d.get_or_create_user_preferences(db, user.id)
        pref.email_enabled = pref.email_consent = True
        row = d.enqueue_single_delivery(db, user.id, alert.id, "email", "ALERT_CREATED")
        db.commit()
        return factory, row.id, user.id, alert.id


def claim(factory, identity):
    with factory() as db:
        return d.claim_pending_deliveries(db, delivery_id=identity)[0]


def test_atomic_workers_and_fencing(delivery):
    factory, identity, uid, _ = delivery
    barrier = Barrier(2)
    def race():
        with factory() as db:
            barrier.wait(timeout=10)
            return d.claim_pending_deliveries(db, user_id=uid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: race(), range(2)))
    assert sorted(map(len, results)) == [0, 1]
    old = next(rows[0] for rows in results if rows)
    with factory() as db:
        row = db.get(NotificationDelivery, identity)
        row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    fresh = claim(factory, identity)
    assert fresh.claim_token != old.claim_token
    with factory() as db, patch.object(d, "get_email_sender") as sender:
        # Attach the stale snapshot without refreshing it.
        old = db.merge(old, load=False)
        old._worker_token = results[0][0]._worker_token if results[0] else results[1][0]._worker_token
        assert not d.process_single_delivery(db, old)
        sender.assert_not_called()
    with factory() as db:
        current = db.get(NotificationDelivery, identity)
        current._worker_token = fresh._worker_token
        TestEmailSender.clear()
        assert d.process_single_delivery(db, current)
        assert current.status == "SENT"
        assert not d.process_single_delivery(db, current)
        assert len(TestEmailSender.get_sent_messages()) == 1
        assert d.claim_pending_deliveries(db, delivery_id=identity) == []


@pytest.mark.parametrize("result,status", [
    (EmailSendResult(True, "test"), "SENT"),
    (EmailSendResult(False, "test", "SECRET recipient", True, "transient"), "FAILED"),
    (EmailSendResult(False, "test", "SECRET recipient", False, "invalid_recipient"), "DEAD_LETTER"),
    (EmailSendResult(False, "test", "SECRET", True, "rate_limited", 7200), "FAILED"),
])
def test_provider_outcomes_and_no_transaction(delivery, result, status, caplog):
    factory, identity, _, _ = delivery
    claim(factory, identity)
    with factory() as db:
        row = db.get(NotificationDelivery, identity)
        row._worker_token = row.claim_token
        def send(message):
            assert not db.in_transaction()
            assert message.headers["X-Idempotency-Key"] == row_key
            return result
        row_key = row.idempotency_key
        before = datetime.now(timezone.utc)
        with patch.object(d, "get_email_sender") as provider:
            provider.return_value.send.side_effect = send
            assert d.process_single_delivery(db, row) == result.success
        assert row.status == status
        assert "SECRET" not in (row.failure_reason or "") + caplog.text
        if status == "FAILED":
            assert row.next_attempt_at > before
            if result.retry_after_seconds:
                assert row.next_attempt_at >= before + timedelta(seconds=7200)
            assert d.claim_pending_deliveries(db, delivery_id=identity) == []
            row.next_attempt_at = before - timedelta(seconds=1)
            db.commit()
            retry = d.claim_pending_deliveries(db, delivery_id=identity)[0]
            with patch.object(d, "get_email_sender", return_value=TestEmailSender()):
                assert d.process_single_delivery(db, retry)
            assert retry.idempotency_key == row_key
            assert db.query(NotificationDelivery).filter_by(id=identity).count() == 1


def test_timeout_exhaustion_and_preference_recheck(delivery):
    factory, identity, uid, _ = delivery
    claim(factory, identity)
    with factory() as db:
        row = db.get(NotificationDelivery, identity)
        row._worker_token = row.claim_token
        row.max_attempts = 1
        db.commit()
        with patch.object(d, "get_email_sender") as sender:
            sender.return_value.send.side_effect = TimeoutError("secret")
            assert not d.process_single_delivery(db, row)
        assert row.status == "DEAD_LETTER"
        assert "secret" not in row.failure_reason
        row.status, row.attempt_count = "PENDING", 0
        pref = d.get_or_create_user_preferences(db, uid)
        pref.email_consent = False
        db.commit()
        row = d.claim_pending_deliveries(db, delivery_id=identity)[0]
        with patch.object(d, "get_email_sender") as sender:
            assert not d.process_single_delivery(db, row)
            sender.assert_not_called()
        assert row.status == "SUPPRESSED"


def test_exhausted_abandoned_legacy_claim(delivery):
    factory, identity, _, _ = delivery
    with factory() as db:
        row = db.get(NotificationDelivery, identity)
        row.status, row.attempt_count = "PROCESSING", row.max_attempts
        db.commit()
        assert d.claim_pending_deliveries(db, delivery_id=identity) == []
        db.refresh(row)
        assert row.status == "DEAD_LETTER"


def test_duplicate_creation_and_caller_rollback(delivery):
    factory, identity, uid, aid = delivery
    with factory() as db:
        row = d.enqueue_single_delivery(db, uid, aid, "email", "ALERT_CREATED")
        assert row.id == identity
        extra = d.enqueue_single_delivery(db, uid, aid, "in_app", "ALERT_CREATED")
        extra_id = extra.id
        db.rollback()
    with factory() as db:
        assert db.get(NotificationDelivery, extra_id) is None
        assert db.get(NotificationDelivery, identity) is not None


def test_owner_scoped_status_and_private_claim(delivery):
    factory, identity, uid, _ = delivery
    def get_test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = get_test_db
    try:
        with TestClient(app) as client, factory() as db:
            other = User(email=uuid4().hex + "@example.com", hashed_password="test", email_verified=True)
            db.add(other); db.commit()
            def headers(user):
                return {"Authorization": "Bearer " + create_access_token({"sub": user.email, "user_id": user.id})}
            path = "/finance/notification-deliveries"
            assert client.get(path).status_code == 401
            own = client.get(path, headers=headers(db.get(User, uid))).json()
            item = next(x for x in own["items"] if x["id"] == identity)
            assert item["status"] == "PENDING"
            assert "claim_token" not in item and "lease_expires_at" not in item
            assert client.get(path, headers=headers(other)).json()["items"] == []
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_migration_roundtrip_preserves_records(delivery):
    factory, identity, _, _ = delivery
    config = Config("alembic.ini")
    command.downgrade(config, "f17f00000001")
    command.upgrade(config, "head")
    with factory() as db:
        row = db.get(NotificationDelivery, identity)
        assert row.status == "PENDING" and row.claim_token is None


@pytest.mark.parametrize("code,transient", [(421, True), (450, True), (550, False), (535, False)])
def test_smtp_response_classification(code, transient):
    msg = EmailMessage("test@example.com", "Subject", "Body", "<p>Body</p>")
    with patch("smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.side_effect = smtplib.SMTPDataError(code, b"secret")
        result = SmtpEmailSender().send(msg)
    assert result.is_transient == transient and not result.success
    assert "secret" not in result.error_message


def test_backoff_cap_jitter_and_provider_minimum():
    assert d.compute_retry_delay(2) > d.compute_retry_delay(1)
    assert d.compute_retry_delay(100).total_seconds() == d.settings.NOTIFICATION_RETRY_MAX_DELAY_SECONDS
    with patch.object(d.random, "uniform", return_value=5):
        assert d.compute_retry_delay(1, jitter=True).total_seconds() == 65
    assert d.compute_retry_delay(1, 7200).total_seconds() == 7200


def test_parallel_workers_deliver_distinct_rows_once(delivery):
    factory, identity, uid, aid = delivery
    with factory() as db:
        second = d.enqueue_single_delivery(db, uid, aid, "email", "ALERT_RECURRED", occurrence_count=2)
        db.commit()
        second_id = second.id
    barrier = Barrier(2)
    accepted = []
    def send(message):
        barrier.wait(timeout=10)
        accepted.append(message.headers["X-Idempotency-Key"])
        return EmailSendResult(True, "test")
    def worker():
        with factory() as db:
            rows = d.claim_pending_deliveries(db, user_id=uid, limit=1)
            assert len(rows) == 1
            return d.process_single_delivery(db, rows[0])
    with patch.object(d, "get_email_sender") as provider:
        provider.return_value.send.side_effect = send
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
    assert results == [True, True] and len(set(accepted)) == 2
    with factory() as db:
        assert all(db.get(NotificationDelivery, i).status == "SENT" for i in [identity, second_id])


def test_expiry_during_provider_call_fences_completion(delivery):
    factory, identity, _, _ = delivery
    claim(factory, identity)
    with factory() as db:
        row = db.get(NotificationDelivery, identity)
        row._worker_token = row.claim_token
        original_token = row.claim_token
        def send(_):
            with factory() as other:
                current = other.get(NotificationDelivery, identity)
                current.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                other.commit()
            replacement = claim(factory, identity)
            assert replacement.claim_token != original_token
            return EmailSendResult(True, "test")
        with patch.object(d, "get_email_sender") as provider:
            provider.return_value.send.side_effect = send
            assert not d.process_single_delivery(db, row)
        db.refresh(row)
        assert row.status == "PROCESSING" and row.claim_token != original_token


def test_duplicate_event_race_preserves_caller_transaction(delivery):
    factory, _, uid, aid = delivery
    barrier = Barrier(2)
    def enqueue():
        with factory() as db:
            marker = User(email=uuid4().hex + "@example.com", hashed_password="marker")
            db.add(marker); db.flush()
            marker_id = marker.id
            barrier.wait(timeout=10)
            row = d.enqueue_single_delivery(db, uid, aid, "in_app", "ALERT_RECURRED", occurrence_count=3)
            identity = row.id
            db.commit()
            return identity, marker_id
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: enqueue(), range(2)))
    assert results[0][0] == results[1][0]
    with factory() as db:
        assert all(db.get(User, marker) is not None for _, marker in results)


def test_periodic_worker_drains_backlog_beyond_one_batch(delivery):
    from app.services.notifications import worker
    factory, _, uid, aid = delivery
    with factory() as db:
        for occurrence in range(1, 26):
            d.enqueue_single_delivery(db, uid, aid, "in_app", "ALERT_RECURRED", occurrence_count=occurrence)
        db.commit()
    # The shared module schema contains other tests' intentionally abandoned rows.
    # Keep this backlog count scoped to its owner while exercising the real claimant.
    scoped_claim = lambda db, limit: d.claim_pending_deliveries(db, limit=limit, user_id=uid)
    with patch.object(worker, "SessionLocal", factory), patch.object(d.settings, "NOTIFICATION_BATCH_SIZE", 20), patch.object(worker, "claim_pending_deliveries", scoped_claim):
        assert worker.run_once() == 20
        assert worker.run_once() == 6
        assert worker.run_once() == 0
    with factory() as db:
        assert db.query(NotificationDelivery).filter_by(user_id=uid, status="SENT").count() == 26


def test_digest_opt_out_is_rechecked(delivery):
    from app.services.notifications.digest_engine import generate_daily_digest_for_user
    factory, _, uid, _ = delivery
    with factory() as db:
        pref = d.get_or_create_user_preferences(db, uid)
        pref.daily_digest_enabled = True
        db.commit()
        digest, _ = generate_daily_digest_for_user(db, uid, force=True)
        assert digest is not None
        db.commit()
        row = db.query(NotificationDelivery).filter_by(digest_id=digest.id).one()
        identity = row.id
        pref.email_consent = False
        db.commit()
        claimed = d.claim_pending_deliveries(db, delivery_id=identity)[0]
        with patch.object(d, "get_email_sender") as sender:
            assert not d.process_single_delivery(db, claimed)
            sender.assert_not_called()
        db.refresh(digest)
        assert claimed.status == "SUPPRESSED" and digest.status == "FAILED"


@pytest.mark.parametrize("source_status", ["resolved", "dismissed"])
def test_inactive_alert_is_suppressed_at_send_time(delivery, source_status):
    factory, identity, _, aid = delivery
    with factory() as db:
        alert = db.get(FinancialAlert, aid)
        alert.status = source_status
        db.commit()
        row = d.claim_pending_deliveries(db, delivery_id=identity)[0]
        with patch.object(d, "get_email_sender") as sender:
            assert not d.process_single_delivery(db, row)
            sender.assert_not_called()
        assert row.status == "SUPPRESSED"
