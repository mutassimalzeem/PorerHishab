"""Synthetic delivery lifecycle against the runner's real API and disposable PostgreSQL."""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from seed_financial_review_e2e import validate_database


def main():
    validate_database(os.environ.get("DATABASE_URL", "sqlite://"))
    from app.core.database import SessionLocal
    from app.models import User
    from app.models.financial_alert import FinancialAlert
    from app.models.notification_delivery import NotificationDelivery
    from app.services.notifications import dispatcher as d
    from app.services.notifications.worker import run_once
    from app.services.notifications.email_sender import TestEmailSender, EmailSendResult

    def api(path, data=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = Request("http://127.0.0.1:8019" + path,
                      data=json.dumps(data).encode() if data else None, headers=headers)
        with urlopen(req, timeout=20) as response:
            return json.load(response)

    token = api("/login", {"email": "review@example.com", "password": "Review-E2E-only-123!"})["access_token"]
    with SessionLocal() as db:
        user = db.query(User).filter_by(email="review@example.com").one()
        # This validated disposable fixture represents a mailbox-confirmed user.
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        pref = d.get_or_create_user_preferences(db, user.id)
        pref.email_enabled = pref.email_consent = True
        ids = []
        for name in ["success", "retry", "permanent"]:
            alert = FinancialAlert(user_id=user.id, alert_key="delivery-e2e:" + name,
                alert_type="cash_shortfall", severity="critical", title="Synthetic delivery",
                title_key="test", message="Open the app to review.", message_key="test",
                recommended_action="Review", status="active")
            db.add(alert); db.flush()
            row = d.enqueue_single_delivery(db, user.id, alert.id, "email", "ALERT_CREATED")
            ids.append(row.id)
        db.commit()
    initial = api("/finance/notification-deliveries?limit=100", token=token)["items"]
    assert all(next(r for r in initial if r["id"] == i)["status"] == "PENDING" for i in ids)
    accepted = TestEmailSender()
    seen = []
    def send(message):
        key = message.headers["X-Idempotency-Key"]
        seen.append(key)
        if len(seen) == 2:
            return EmailSendResult(False, "test", is_transient=True, failure_category="rate_limited", retry_after_seconds=60)
        if len(seen) == 3:
            return EmailSendResult(False, "test", failure_category="invalid_recipient")
        return accepted.send(message)
    TestEmailSender.clear()
    with patch.object(d, "get_email_sender") as provider:
        provider.return_value.send.side_effect = send
        assert run_once() == 1
        rows = api("/finance/notification-deliveries?limit=100", token=token)["items"]
        assert [next(r for r in rows if r["id"] == i)["status"] for i in ids] == ["SENT", "FAILED", "DEAD_LETTER"]
        assert run_once() == 0
        with SessionLocal() as db:
            row = db.get(NotificationDelivery, ids[1])
            row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        assert run_once() == 1
        assert run_once() == 0
    assert len(TestEmailSender.get_sent_messages()) == 2
    assert seen[1] == seen[3]
    rows = api("/finance/notification-deliveries?limit=100", token=token)["items"]
    assert [next(r for r in rows if r["id"] == i)["status"] for i in ids] == ["SENT", "SENT", "DEAD_LETTER"]
    print("Notification real-stack lifecycle: acceptance, persisted retry, stable identity, terminal failure passed")


if __name__ == "__main__":
    main()
