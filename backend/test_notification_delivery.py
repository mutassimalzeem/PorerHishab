"""Comprehensive unit, integration, security, and concurrency tests for AI-15M Notification Delivery Infrastructure."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from zoneinfo import ZoneInfo

from app.api.auth import create_access_token
from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.account import Account
from app.models.financial_alert import FinancialAlert
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.services.intelligence.periods import today_dhaka
from app.models.notification_delivery import NotificationDelivery
from app.models.notification_preference import NotificationPreference
from app.models.user import User
from app.services.finance.financial_alerts import evaluate_alerts
from app.services.notifications.dispatcher import (
    claim_pending_deliveries,
    compute_retry_delay,
    dispatch_pending_user_deliveries,
    enqueue_notifications_for_alert,
    enqueue_single_delivery,
    generate_idempotency_key,
    get_or_create_user_preferences,
    process_claimed_deliveries,
    process_single_delivery,
)
from app.services.notifications.eligibility import (
    EligibilityReason,
    calculate_quiet_hours_window,
    evaluate_eligibility,
)
from app.services.notifications.email_content import build_privacy_safe_alert_email
from app.services.notifications.email_sender import (
    EmailMessage,
    SmtpEmailSender,
    TestEmailSender,
    get_email_sender,
)

client = TestClient(app)


def make_user(db: SessionLocal, email: str | None = None) -> User:
    user = User(
        email=email or f"notif-user-{uuid4()}@example.com",
        hashed_password="test-password",
        full_name="Notification Test User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": user.email, "user_id": user.id})
    return {"Authorization": f"Bearer {token}"}


def cleanup(db: SessionLocal, *users: User) -> None:
    for u in users:
        if u is not None:
            db.query(NotificationDelivery).filter(NotificationDelivery.user_id == u.id).delete()
            db.query(NotificationPreference).filter(NotificationPreference.user_id == u.id).delete()
            db.query(FinancialAlert).filter(FinancialAlert.user_id == u.id).delete()
            db.query(ScheduledCashflowItem).filter(ScheduledCashflowItem.user_id == u.id).delete()
            db.query(Account).filter(Account.user_id == u.id).delete()
            db.delete(u)
    db.commit()


# ============================================================================
# 1. Unit Tests: Notification Preferences & Eligibility
# ============================================================================


def test_preference_defaults():
    """Default preferences must be conservative and privacy-first."""
    pref = NotificationPreference(user_id=1)
    assert pref.in_app_enabled is True
    assert pref.in_app_min_severity == "info"
    # Email must be disabled and require explicit consent by default
    assert pref.email_enabled is False
    assert pref.email_consent is False
    assert pref.email_consent_at is None
    assert pref.email_min_severity == "warning"
    assert pref.quiet_hours_enabled is False
    assert pref.quiet_hours_start == "22:00"
    assert pref.quiet_hours_end == "07:00"
    assert pref.timezone == "Asia/Dhaka"
    assert pref.frequency_mode == "immediate"


def test_eligibility_channel_disabled():
    """Disabled channels must return DISABLED."""
    pref = NotificationPreference(user_id=1, in_app_enabled=False, email_enabled=False)

    in_app_res = evaluate_eligibility(
        pref, channel="in_app", alert_severity="critical", notification_event="ALERT_CREATED"
    )
    assert in_app_res.is_eligible is False
    assert in_app_res.reason == EligibilityReason.DISABLED

    # If email consent is given but channel disabled -> DISABLED
    pref.email_consent = True
    email_res = evaluate_eligibility(
        pref, channel="email", alert_severity="critical", notification_event="ALERT_CREATED"
    )
    assert email_res.is_eligible is False
    assert email_res.reason == EligibilityReason.DISABLED


def test_eligibility_email_consent_required():
    """Email delivery must require explicit consent even if email is enabled."""
    pref = NotificationPreference(user_id=1, email_enabled=True, email_consent=False)

    res = evaluate_eligibility(
        pref, channel="email", alert_severity="critical", notification_event="ALERT_CREATED"
    )
    assert res.is_eligible is False
    assert res.reason == EligibilityReason.NO_CONSENT


def test_eligibility_severity_thresholds():
    """Alerts below minimum severity threshold must be suppressed."""
    pref = NotificationPreference(
        user_id=1,
        email_enabled=True,
        email_consent=True,
        email_min_severity="warning",
        in_app_enabled=True,
        in_app_min_severity="critical",
    )

    # Info alert with warning minimum email threshold
    res_info = evaluate_eligibility(
        pref, channel="email", alert_severity="info", notification_event="ALERT_CREATED"
    )
    assert res_info.is_eligible is False
    assert res_info.reason == EligibilityReason.BELOW_SEVERITY_THRESHOLD

    # Low alert with warning minimum email threshold
    res_low = evaluate_eligibility(
        pref, channel="email", alert_severity="low", notification_event="ALERT_CREATED"
    )
    assert res_low.is_eligible is False
    assert res_low.reason == EligibilityReason.BELOW_SEVERITY_THRESHOLD

    # Medium/Warning alert with warning minimum email threshold
    res_med = evaluate_eligibility(
        pref, channel="email", alert_severity="medium", notification_event="ALERT_CREATED"
    )
    assert res_med.is_eligible is True

    # High alert with warning minimum email threshold
    res_high = evaluate_eligibility(
        pref, channel="email", alert_severity="high", notification_event="ALERT_CREATED"
    )
    assert res_high.is_eligible is True

    # In-app with critical threshold: warning is below critical
    res_in_app = evaluate_eligibility(
        pref, channel="in_app", alert_severity="warning", notification_event="ALERT_CREATED"
    )
    assert res_in_app.is_eligible is False
    assert res_in_app.reason == EligibilityReason.BELOW_SEVERITY_THRESHOLD


def test_eligibility_frequency_modes():
    """Frequency modes OFF and DAILY_DIGEST must suppress immediate dispatch."""
    pref = NotificationPreference(
        user_id=1,
        email_enabled=True,
        email_consent=True,
        email_min_severity="info",
        frequency_mode="off",
    )
    res_off = evaluate_eligibility(
        pref, channel="email", alert_severity="critical", notification_event="ALERT_CREATED"
    )
    assert res_off.is_eligible is False
    assert res_off.reason == EligibilityReason.FREQUENCY_SUPPRESSED

    pref.frequency_mode = "daily_digest"
    res_digest = evaluate_eligibility(
        pref, channel="email", alert_severity="critical", notification_event="ALERT_CREATED"
    )
    assert res_digest.is_eligible is False
    assert res_digest.reason == EligibilityReason.FREQUENCY_SUPPRESSED


def test_eligibility_quiet_hours_overnight_window():
    """Overnight quiet hours window (22:00 -> 07:00) must defer non-critical and allow critical."""
    tz = "Asia/Dhaka"  # UTC+6
    pref = NotificationPreference(
        user_id=1,
        email_enabled=True,
        email_consent=True,
        email_min_severity="info",
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="07:00",
        timezone=tz,
    )

    # 1. At 23:30 Dhaka time (17:30 UTC): within quiet hours
    dt_2330 = datetime(2026, 11, 1, 17, 30, tzinfo=timezone.utc)
    res_warning = evaluate_eligibility(
        pref, channel="email", alert_severity="warning", notification_event="ALERT_CREATED", now_utc=dt_2330
    )
    assert res_warning.is_eligible is False
    assert res_warning.reason == EligibilityReason.QUIET_HOURS
    assert res_warning.next_eligible_at is not None
    # Next eligible time should be 07:00 tomorrow Dhaka time (01:00 UTC)
    expected_wake = datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)
    assert res_warning.next_eligible_at == expected_wake

    # 2. CRITICAL alert at 23:30 Dhaka time must bypass quiet hours
    res_critical = evaluate_eligibility(
        pref, channel="email", alert_severity="critical", notification_event="ALERT_CREATED", now_utc=dt_2330
    )
    assert res_critical.is_eligible is True
    assert res_critical.reason == EligibilityReason.ELIGIBLE

    # 3. At 03:00 Dhaka time (21:00 UTC prev day): within overnight quiet hours
    dt_0300 = datetime(2026, 11, 1, 21, 0, tzinfo=timezone.utc)
    res_0300 = evaluate_eligibility(
        pref, channel="email", alert_severity="warning", notification_event="ALERT_CREATED", now_utc=dt_0300
    )
    assert res_0300.is_eligible is False
    assert res_0300.reason == EligibilityReason.QUIET_HOURS
    # Next eligible is 07:00 today Dhaka time (01:00 UTC)
    assert res_0300.next_eligible_at == datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)

    # 4. At 07:00 Dhaka time (01:00 UTC): window has ended
    dt_0700 = datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)
    res_0700 = evaluate_eligibility(
        pref, channel="email", alert_severity="warning", notification_event="ALERT_CREATED", now_utc=dt_0700
    )
    assert res_0700.is_eligible is True

    # 5. At 15:00 Dhaka time (09:00 UTC): daytime, outside window
    dt_1500 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
    res_1500 = evaluate_eligibility(
        pref, channel="email", alert_severity="warning", notification_event="ALERT_CREATED", now_utc=dt_1500
    )
    assert res_1500.is_eligible is True


def test_eligibility_quiet_hours_daytime_window():
    """Standard daytime window (e.g. 13:00 -> 14:00) must work deterministically."""
    pref = NotificationPreference(
        user_id=1,
        in_app_enabled=True,
        in_app_min_severity="info",
        quiet_hours_enabled=True,
        quiet_hours_start="13:00",
        quiet_hours_end="14:00",
        timezone="UTC",
    )
    # At 13:30 UTC -> inside
    res_in = evaluate_eligibility(
        pref, channel="in_app", alert_severity="info", notification_event="ALERT_CREATED",
        now_utc=datetime(2026, 11, 1, 13, 30, tzinfo=timezone.utc)
    )
    assert res_in.is_eligible is False
    assert res_in.reason == EligibilityReason.QUIET_HOURS
    assert res_in.next_eligible_at == datetime(2026, 11, 1, 14, 0, tzinfo=timezone.utc)

    # At 14:00 UTC -> outside
    res_out = evaluate_eligibility(
        pref, channel="in_app", alert_severity="info", notification_event="ALERT_CREATED",
        now_utc=datetime(2026, 11, 1, 14, 0, tzinfo=timezone.utc)
    )
    assert res_out.is_eligible is True


# ============================================================================
# 2. Unit Tests: Email Privacy Content & Adapters
# ============================================================================


def test_email_privacy_content():
    """Email must never expose balances, transaction amounts, merchant names or raw evidence."""
    alert = FinancialAlert(
        id=42,
        user_id=1,
        alert_key="cash_position:runway_risk",
        alert_type="cash_shortfall",
        severity="critical",
        title="Projected Cash Shortfall",
        title_key="alert_title_cash_shortfall",
        message="Projected cash balance drops to -50000.00 BDT at Dutch Bangla Bank.",
        message_key="alert_msg_cash_shortfall",
        evidence={
            "account_balance": "50000.00",
            "account_name": "Dutch Bangla Bank",
            "transaction_merchant": "Secret Merchant",
            "amount": "120000.00",
        },
        recommended_action="Postpone luxury spending.",
        action_url="/cashflow",
        status="active",
    )

    msg = build_privacy_safe_alert_email(alert, "user@example.com")

    # Subject checks
    assert msg.subject == "PorerHishab critical financial alert"
    assert "50000" not in msg.subject
    assert "Dutch Bangla" not in msg.subject

    # Body checks: must NOT contain sensitive financial evidence
    assert "50000" not in msg.body_text
    assert "Dutch Bangla" not in msg.body_text
    assert "Secret Merchant" not in msg.body_text
    assert "120000" not in msg.body_text
    assert "50000" not in msg.body_html
    assert "Dutch Bangla" not in msg.body_html
    assert "Secret Merchant" not in msg.body_html

    # Must contain generic guidance and authenticated web link
    assert "financial alert" in msg.body_text
    assert "/alerts" in msg.body_text
    assert "/alerts" in msg.body_html


def test_email_sender_test_backend():
    """TestEmailSender captures messages in memory safely without network calls."""
    sender = TestEmailSender()
    TestEmailSender.clear()

    msg = EmailMessage(
        recipient="test@example.com",
        subject="PorerHishab financial alert",
        body_text="Alert text",
        body_html="<p>Alert text</p>",
    )
    result = sender.send(msg)
    assert result.success is True
    assert result.provider == "test"

    sent = TestEmailSender.get_sent_messages()
    assert len(sent) == 1
    assert sent[0].recipient == "test@example.com"
    assert sent[0].subject == "PorerHishab financial alert"

    TestEmailSender.clear()
    assert len(TestEmailSender.get_sent_messages()) == 0


def test_email_sender_invalid_recipient():
    """Invalid recipient addresses must fail permanently."""
    sender = TestEmailSender()
    msg = EmailMessage(
        recipient="invalid-address-without-at",
        subject="Test",
        body_text="Test",
        body_html="<p>Test</p>",
    )
    result = sender.send(msg)
    assert result.success is False
    assert result.failure_category == "invalid_recipient"
    assert result.is_transient is False


def test_smtp_sender_error_classification():
    """SmtpEmailSender must correctly classify transient socket errors and permanent auth errors."""
    sender = SmtpEmailSender(host="non-existent-smtp-host.invalid", port=587, timeout=0.1)
    msg = EmailMessage(
        recipient="test@example.com",
        subject="Test",
        body_text="Test",
        body_html="<p>Test</p>",
    )
    result = sender.send(msg)
    assert result.success is False
    assert result.provider == "smtp"
    # Network/connect failures are transient
    assert result.is_transient is True
    assert result.failure_category == "transient"


# ============================================================================
# 3. Unit Tests: Idempotency & Retries
# ============================================================================


def test_idempotency_key_deterministic():
    """Idempotency key must be deterministic, user-scoped, and contain no timestamps."""
    key1 = generate_idempotency_key(10, 42, "email", "ALERT_CREATED")
    key2 = generate_idempotency_key(10, 42, "EMAIL", "alert_created")
    assert key1 == key2
    assert key1 == "usr_10:alt_42:chn_email:evt_ALERT_CREATED"

    # Different user must have different key
    key3 = generate_idempotency_key(11, 42, "email", "ALERT_CREATED")
    assert key1 != key3


def test_retry_delay_bounded():
    """Retry delay must follow configured backoff steps and remain bounded."""
    delay1 = compute_retry_delay(1)
    delay2 = compute_retry_delay(2)
    delay3 = compute_retry_delay(3)
    delay_large = compute_retry_delay(100)

    assert delay1 == timedelta(seconds=60)
    assert delay2 == timedelta(seconds=300)
    assert delay3 == timedelta(seconds=900)
    assert delay_large == timedelta(seconds=900)


# ============================================================================
# 4. API Contract Tests: Preferences & Deliveries
# ============================================================================


def test_preferences_api_requires_auth():
    """Preferences endpoints must reject unauthenticated requests with 401."""
    res_get = client.get("/finance/notification-preferences")
    assert res_get.status_code == 401

    res_put = client.put("/finance/notification-preferences", json={"in_app_enabled": False})
    assert res_put.status_code == 401

    res_deliv = client.get("/finance/notification-deliveries")
    assert res_deliv.status_code == 401


def test_preferences_api_crud_flow():
    """Authenticated user can read, update, and manage notification preferences."""
    db = SessionLocal()
    user = make_user(db)
    headers = auth_headers(user)

    try:
        # 1. GET returns initialized defaults
        get_res = client.get("/finance/notification-preferences", headers=headers)
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["user_id"] == user.id
        assert data["in_app_enabled"] is True
        assert data["email_enabled"] is False
        assert data["email_consent"] is False
        assert data["email_consent_at"] is None

        # 2. PUT updates fields and sets email_consent_at
        update_payload = {
            "email_enabled": True,
            "email_consent": True,
            "email_min_severity": "critical",
            "quiet_hours_enabled": True,
            "quiet_hours_start": "23:00",
            "quiet_hours_end": "08:00",
            "timezone": "Asia/Dhaka",
            "frequency_mode": "immediate",
        }
        put_res = client.put(
            "/finance/notification-preferences",
            json=update_payload,
            headers=headers,
        )
        assert put_res.status_code == 200
        updated = put_res.json()
        assert updated["email_enabled"] is True
        assert updated["email_consent"] is True
        assert updated["email_consent_at"] is not None
        assert updated["email_min_severity"] == "critical"
        assert updated["quiet_hours_start"] == "23:00"
        assert updated["quiet_hours_end"] == "08:00"

        # 3. Revoking consent clears email_consent_at
        put_revoke = client.put(
            "/finance/notification-preferences",
            json={"email_consent": False},
            headers=headers,
        )
        assert put_revoke.status_code == 200
        assert put_revoke.json()["email_consent"] is False
        assert put_revoke.json()["email_consent_at"] is None

    finally:
        cleanup(db, user)
        db.close()


def test_preferences_validation_errors():
    """Invalid time format, timezone, or enum values must be rejected with 422."""
    db = SessionLocal()
    user = make_user(db)
    headers = auth_headers(user)

    try:
        # Invalid time format (e.g. 25:00)
        res_bad_time = client.put(
            "/finance/notification-preferences",
            json={"quiet_hours_start": "25:00"},
            headers=headers,
        )
        assert res_bad_time.status_code == 422

        # Invalid timezone
        res_bad_tz = client.put(
            "/finance/notification-preferences",
            json={"timezone": "Invalid/Fake_Zone"},
            headers=headers,
        )
        assert res_bad_tz.status_code == 422

        # Invalid frequency mode
        res_bad_freq = client.put(
            "/finance/notification-preferences",
            json={"frequency_mode": "invalid_mode"},
            headers=headers,
        )
        assert res_bad_freq.status_code == 422

    finally:
        cleanup(db, user)
        db.close()


def test_notification_deliveries_api():
    """Deliveries endpoint returns owner-scoped history with pagination and filtering."""
    db = SessionLocal()
    user = make_user(db)
    headers = auth_headers(user)

    try:
        # Create an alert and delivery
        alert = FinancialAlert(
            user_id=user.id,
            alert_key="cash:test_deliv",
            alert_type="test",
            severity="critical",
            title="Test",
            title_key="test",
            message="Test msg",
            message_key="test",
            evidence={},
            recommended_action="Act",
            status="active",
        )
        db.add(alert)
        db.flush()

        d1 = enqueue_single_delivery(db, user.id, alert.id, "in_app", "ALERT_CREATED", "SENT")
        d2 = enqueue_single_delivery(db, user.id, alert.id, "email", "ALERT_CREATED", "PENDING")
        db.commit()

        # Query all
        res = client.get("/finance/notification-deliveries", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

        # Query by channel
        res_email = client.get("/finance/notification-deliveries?channel=email", headers=headers)
        assert res_email.status_code == 200
        assert res_email.json()["total"] == 1
        assert res_email.json()["items"][0]["channel"] == "email"

        # Query by status
        res_sent = client.get("/finance/notification-deliveries?status=SENT", headers=headers)
        assert res_sent.status_code == 200
        assert res_sent.json()["total"] == 1
        assert res_sent.json()["items"][0]["status"] == "SENT"

    finally:
        cleanup(db, user)
        db.close()


# ============================================================================
# 5. Security Tests: Strict User Scoping & Isolation
# ============================================================================


def test_user_isolation_preferences_and_deliveries():
    """User A must NEVER read, update, or affect User B's preferences or deliveries."""
    db = SessionLocal()
    user_a = make_user(db, "usera@example.com")
    user_b = make_user(db, "userb@example.com")
    headers_a = auth_headers(user_a)
    headers_b = auth_headers(user_b)

    try:
        # User B sets distinct preferences
        client.put(
            "/finance/notification-preferences",
            json={"email_enabled": True, "email_consent": True, "quiet_hours_start": "23:45"},
            headers=headers_b,
        )

        # User A reads preferences: must see their own, untouched defaults
        res_a = client.get("/finance/notification-preferences", headers=headers_a)
        assert res_a.json()["user_id"] == user_a.id
        assert res_a.json()["email_enabled"] is False
        assert res_a.json()["quiet_hours_start"] == "22:00"

        # Create delivery for user B
        alert_b = FinancialAlert(
            user_id=user_b.id,
            alert_key="cash:b",
            alert_type="test",
            severity="info",
            title="B",
            title_key="b",
            message="B",
            message_key="b",
            evidence={},
            recommended_action="B",
            status="active",
        )
        db.add(alert_b)
        db.flush()
        enqueue_single_delivery(db, user_b.id, alert_b.id, "in_app", "ALERT_CREATED", "SENT")
        db.commit()

        # User A queries deliveries: must see 0 items
        res_deliv_a = client.get("/finance/notification-deliveries", headers=headers_a)
        assert res_deliv_a.json()["total"] == 0
        assert len(res_deliv_a.json()["items"]) == 0

    finally:
        cleanup(db, user_a, user_b)
        db.close()


# ============================================================================
# 6. PostgreSQL Concurrency & Idempotency Tests
# ============================================================================


def test_concurrent_delivery_creation_idempotency():
    """Four concurrent threads attempting to enqueue the same logical delivery must produce exactly ONE row."""
    db = SessionLocal()
    user = make_user(db)

    try:
        alert = FinancialAlert(
            user_id=user.id,
            alert_key="concurrency:test",
            alert_type="test",
            severity="critical",
            title="Concurrent Test",
            title_key="test",
            message="Test msg",
            message_key="test",
            evidence={},
            recommended_action="Act",
            status="active",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alert_id = alert.id
        user_id = user.id

        def worker_enqueue(thread_idx: int) -> int:
            worker_db = SessionLocal()
            try:
                delivery = enqueue_single_delivery(
                    worker_db,
                    user_id=user_id,
                    alert_id=alert_id,
                    channel="email",
                    notification_event="ALERT_CREATED",
                )
                worker_db.commit()
                return delivery.id
            finally:
                worker_db.close()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker_enqueue, i) for i in range(4)]
            delivery_ids = [f.result() for f in futures]

        # All workers must return the exact same delivery ID
        assert len(set(delivery_ids)) == 1

        # Check database: exactly one delivery row exists
        deliveries = (
            db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.user_id == user_id,
                NotificationDelivery.alert_id == alert_id,
                NotificationDelivery.channel == "email",
                NotificationDelivery.notification_event == "ALERT_CREATED",
            )
            .all()
        )
        assert len(deliveries) == 1

    finally:
        cleanup(db, user)
        db.close()


def test_different_users_independent_deliveries():
    """Two different users can independently create delivery records for equivalent alerts."""
    db = SessionLocal()
    user1 = make_user(db)
    user2 = make_user(db)

    try:
        alert1 = FinancialAlert(
            user_id=user1.id,
            alert_key="shared_key:test",
            alert_type="test",
            severity="critical",
            title="T",
            title_key="t",
            message="M",
            message_key="m",
            evidence={},
            recommended_action="A",
            status="active",
        )
        alert2 = FinancialAlert(
            user_id=user2.id,
            alert_key="shared_key:test",
            alert_type="test",
            severity="critical",
            title="T",
            title_key="t",
            message="M",
            message_key="m",
            evidence={},
            recommended_action="A",
            status="active",
        )
        db.add_all([alert1, alert2])
        db.commit()

        d1 = enqueue_single_delivery(db, user1.id, alert1.id, "email", "ALERT_CREATED")
        d2 = enqueue_single_delivery(db, user2.id, alert2.id, "email", "ALERT_CREATED")
        db.commit()

        assert d1.id != d2.id
        assert d1.user_id == user1.id
        assert d2.user_id == user2.id

    finally:
        cleanup(db, user1, user2)
        db.close()


def test_concurrent_worker_claiming_skip_locked():
    """Concurrent workers claiming pending deliveries must not double-claim or double-increment attempts."""
    db = SessionLocal()
    user = make_user(db)

    try:
        alert = FinancialAlert(
            user_id=user.id,
            alert_key="claim:test",
            alert_type="test",
            severity="critical",
            title="T",
            title_key="t",
            message="M",
            message_key="m",
            evidence={},
            recommended_action="A",
            status="active",
        )
        db.add(alert)
        db.flush()

        # Enqueue 4 distinct deliveries
        d1 = enqueue_single_delivery(db, user.id, alert.id, "in_app", "ALERT_CREATED", "PENDING")
        d2 = enqueue_single_delivery(db, user.id, alert.id, "in_app", "ALERT_ESCALATED", "PENDING")
        d3 = enqueue_single_delivery(db, user.id, alert.id, "in_app", "ALERT_RECURRED", "PENDING")
        d4 = enqueue_single_delivery(db, user.id, alert.id, "email", "ALERT_CREATED", "PENDING")
        db.commit()

        user_id = user.id
        def claim_worker(worker_id: int) -> list[int]:
            worker_db = SessionLocal()
            try:
                claimed = claim_pending_deliveries(worker_db, limit=2, user_id=user_id)
                return [c.id for c in claimed]
            finally:
                worker_db.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(claim_worker, 1)
            f2 = executor.submit(claim_worker, 2)
            ids1 = f1.result()
            ids2 = f2.result()

        # No item should be claimed by both workers
        overlap = set(ids1).intersection(set(ids2))
        assert len(overlap) == 0

        # All claimed items must have attempt_count == 1 and status == 'PROCESSING'
        all_claimed_ids = ids1 + ids2
        items = db.query(NotificationDelivery).filter(NotificationDelivery.id.in_(all_claimed_ids)).all()
        for item in items:
            assert item.attempt_count == 1
            assert item.status == "PROCESSING"

    finally:
        cleanup(db, user)
        db.close()


# ============================================================================
# 7. Integration Tests: Alert Lifecycle -> Notification Outbox
# ============================================================================


def test_alert_lifecycle_notification_integration():
    """Alert evaluation must create notification records downstream without altering alert results."""
    db = SessionLocal()
    user = make_user(db)
    TestEmailSender.clear()

    try:
        # 1. Enable email notifications with consent
        pref = get_or_create_user_preferences(db, user.id)
        pref.email_enabled = True
        pref.email_consent = True
        pref.email_min_severity = "info"
        db.commit()

        # 2. Create account & obligation to trigger shortfall alert
        today = today_dhaka()
        acc = Account(
            user_id=user.id,
            name='Checking',
            currency='BDT',
            current_balance=Decimal('1000.00'),
            opening_balance=Decimal('1000.00'),
            opening_balance_date=today - timedelta(days=10),
            balance_as_of=datetime.now(timezone.utc),
        )
        db.add(acc)
        item = ScheduledCashflowItem(
            user_id=user.id,
            title='Rent',
            kind='expense',
            amount=Decimal('2500.00'),
            due_date=today + timedelta(days=5),
            status='scheduled',
        )
        db.add(item)
        db.commit()

        summary = evaluate_alerts(db, user.id)
        assert summary.created >= 1

        # Check outbox: deliveries must exist for ALERT_CREATED
        deliveries = (
            db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.user_id == user.id,
                NotificationDelivery.notification_event == "ALERT_CREATED",
            )
            .all()
        )
        assert len(deliveries) >= 1
        channels = {d.channel for d in deliveries}
        assert "in_app" in channels
        assert "email" in channels

        # 3. Repeated unchanged evaluation must NOT duplicate notifications
        summary2 = evaluate_alerts(db, user.id)
        assert summary2.unchanged >= 1

        deliveries_after = (
            db.query(NotificationDelivery)
            .filter(NotificationDelivery.user_id == user.id)
            .all()
        )
        assert len(deliveries_after) == len(deliveries)

        # 4. Process pending user deliveries
        sent_count = dispatch_pending_user_deliveries(user.id)
        assert sent_count >= 1

        # Verify TestEmailSender captured the message
        sent_emails = TestEmailSender.get_sent_messages()
        assert len(sent_emails) >= 1
        assert sent_emails[0].recipient == user.email

        # 5. Verify delivery failures NEVER alter or dismiss the underlying alert
        # Simulate a dead-letter failure on a delivery
        email_deliv = (
            db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.user_id == user.id,
                NotificationDelivery.channel == "email",
            )
            .first()
        )
        email_deliv.status = "DEAD_LETTER"
        email_deliv.failure_reason = "Simulated permanent provider outage"
        db.commit()

        # Alert must remain active and healthy!
        alert = (
            db.query(FinancialAlert)
            .filter(FinancialAlert.id == email_deliv.alert_id)
            .first()
        )
        assert alert.status == "active"
        assert alert.dismissed_at is None
        assert alert.resolved_at is None

    finally:
        cleanup(db, user)
        TestEmailSender.clear()
        db.close()
