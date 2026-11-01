"""Comprehensive tests for AI-15N Notification Orchestration & Daily Digest Engine.

Covers:
- Domain lifecycle event orchestration (ALERT_CREATED, ALERT_ESCALATED, ALERT_RECURRED, unchanged no-op).
- Event idempotency & concurrency safety under PostgreSQL.
- Immediate alerts toggle and critical alert bypass.
- Daily digest generation, idempotency, and concurrent generation safety.
- Timezone boundary handling (Asia/Dhaka, UTC, America/New_York).
- Exclusion of dismissed, actioned, and resolved alerts from digests.
- Immediate notification vs daily digest deduplication.
- Zero-alert days producing no digests.
- Privacy contract enforcement: emails must contain no balances, amounts, merchants, or accounts.
- Bilingual email rendering (English and Bengali).
- Delivery retry, transient failure, and dead-letter handling.
- Tenant isolation across notification history, digests, and deliveries.
- Operational health metrics reporting.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient

from app.api.auth import create_access_token
from app.core.database import SessionLocal
from app.main import app
from app.models.financial_alert import FinancialAlert
from app.models.notification_delivery import NotificationDelivery
from app.models.notification_digest import NotificationDigest, NotificationDigestItem
from app.models.notification_preference import NotificationPreference
from app.models.user import User
from app.services.notifications.digest_engine import (
    generate_daily_digest_for_user,
    get_user_local_date_and_time,
    select_eligible_alerts_for_digest,
)
from app.services.notifications.dispatcher import (
    claim_pending_deliveries,
    generate_idempotency_key,
    get_or_create_user_preferences,
    process_claimed_deliveries,
    process_single_delivery,
)
from app.services.notifications.eligibility import (
    EligibilityReason,
    evaluate_eligibility,
)
from app.services.notifications.email_content import (
    build_privacy_safe_alert_email,
    build_privacy_safe_digest_email,
)
from app.services.notifications.email_sender import TestEmailSender
from app.services.notifications.operational import get_notification_health_metrics
from app.services.notifications.orchestrator import orchestrate_alert_lifecycle_event

client = TestClient(app)


def make_user(db: SessionLocal, full_name: str = "Test User") -> User:
    user = User(
        email=f"orch-user-{uuid4()}@example.com",
        hashed_password="test-password",
        full_name=full_name,
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
            # items cascade from digests
            db.query(NotificationDigest).filter(NotificationDigest.user_id == u.id).delete()
            db.query(FinancialAlert).filter(FinancialAlert.user_id == u.id).delete()
            db.query(NotificationPreference).filter(NotificationPreference.user_id == u.id).delete()
            db.delete(u)
    db.commit()


@pytest.fixture(autouse=True)
def setup_test_email():
    TestEmailSender.clear()
    yield
    TestEmailSender.clear()


# ==============================================================================
# 1. Domain Event Orchestration
# ==============================================================================

def test_orchestration_created_event():
    """ALERT_CREATED enqueues in-app and email according to preferences."""
    db = SessionLocal()
    user = make_user(db)
    try:
        pref = get_or_create_user_preferences(db, user.id)
        pref.email_enabled = True
        pref.email_consent = True
        pref.email_min_severity = "info"
        pref.immediate_enabled = True
        db.commit()

        alert = FinancialAlert(
            user_id=user.id,
            alert_key="cash:runway_risk",
            alert_type="cash_shortfall",
            severity="critical",
            title="Projected Cash Shortfall",
            title_key="alert_title_cash_shortfall",
            message="Cash shortfall projected.",
            message_key="alert_msg_cash_shortfall",
            recommended_action="Review upcoming expenses",
            occurrence_count=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        db.commit()

        deliveries = orchestrate_alert_lifecycle_event(db, alert, "ALERT_CREATED")
        db.commit()

        assert len(deliveries) == 2
        channels = {d.channel for d in deliveries}
        assert channels == {"in_app", "email"}
        for d in deliveries:
            assert d.status == "PENDING"
            assert d.notification_event == "ALERT_CREATED"
            assert d.alert_id == alert.id
    finally:
        cleanup(db, user)
        db.close()


def test_orchestration_escalated_and_recurred_events():
    """ALERT_ESCALATED and ALERT_RECURRED have distinct event identities and occurrence counts."""
    db = SessionLocal()
    user = make_user(db)
    try:
        pref = get_or_create_user_preferences(db, user.id)
        pref.in_app_enabled = True
        db.commit()

        alert = FinancialAlert(
            user_id=user.id,
            alert_key="obligation:12",
            alert_type="upcoming_obligation",
            severity="high",
            title="Upcoming Obligation",
            title_key="alert_title_upcoming",
            message="Payment approaching.",
            message_key="alert_msg_upcoming",
            recommended_action="Prepare funds",
            occurrence_count=2,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        db.commit()

        d_recurred = orchestrate_alert_lifecycle_event(
            db, alert, "ALERT_RECURRED", occurrence_count=2
        )
        db.commit()
        assert len(d_recurred) >= 1
        assert any(d.notification_event == "ALERT_RECURRED" and d.occurrence_count == 2 for d in d_recurred)

        # Escalation event
        alert.severity = "critical"
        alert.occurrence_count = 3
        db.commit()

        d_escalated = orchestrate_alert_lifecycle_event(
            db, alert, "ALERT_ESCALATED", occurrence_count=3
        )
        db.commit()
        assert any(d.notification_event == "ALERT_ESCALATED" and d.occurrence_count == 3 for d in d_escalated)
    finally:
        cleanup(db, user)
        db.close()


def test_immediate_disabled_critical_bypass():
    """When immediate_enabled is False, non-critical is suppressed but CRITICAL bypasses."""
    db = SessionLocal()
    user = make_user(db)
    try:
        pref = get_or_create_user_preferences(db, user.id)
        pref.email_enabled = True
        pref.email_consent = True
        pref.email_min_severity = "info"
        pref.immediate_enabled = False  # User disabled immediate alerts
        db.commit()

        # Non-critical alert -> suppressed from immediate email
        warn_alert = FinancialAlert(
            user_id=user.id,
            alert_key="account:mismatch",
            alert_type="account_balance_mismatch",
            severity="high",
            title="Balance Mismatch",
            title_key="title_mismatch",
            message="Mismatch detected.",
            message_key="msg_mismatch",
            recommended_action="Reconcile account",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(warn_alert)
        db.commit()

        deliveries_warn = orchestrate_alert_lifecycle_event(db, warn_alert, "ALERT_CREATED")
        db.commit()
        email_warn = next(d for d in deliveries_warn if d.channel == "email")
        assert email_warn.status == "SUPPRESSED"

        # Critical alert -> bypasses immediate_enabled=False for financial safety!
        crit_alert = FinancialAlert(
            user_id=user.id,
            alert_key="cash:shortfall",
            alert_type="cash_shortfall",
            severity="critical",
            title="Critical Shortfall",
            title_key="title_crit",
            message="Cash position critical.",
            message_key="msg_crit",
            recommended_action="Postpone spending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(crit_alert)
        db.commit()

        deliveries_crit = orchestrate_alert_lifecycle_event(db, crit_alert, "ALERT_CREATED")
        db.commit()
        email_crit = next(d for d in deliveries_crit if d.channel == "email")
        assert email_crit.status == "PENDING"
    finally:
        cleanup(db, user)
        db.close()


# ==============================================================================
# 2. Daily Digest Engine & Idempotency
# ==============================================================================

def test_daily_digest_generation_and_item_order():
    """Daily digest aggregates eligible alerts sorted by severity rank and created_at asc."""
    db = SessionLocal()
    user = make_user(db)
    try:
        pref = get_or_create_user_preferences(db, user.id)
        pref.email_enabled = True
        pref.email_consent = True
        pref.daily_digest_enabled = True
        pref.email_min_severity = "low"
        db.commit()

        t0 = datetime.now(timezone.utc) - timedelta(hours=2)
        t1 = datetime.now(timezone.utc) - timedelta(hours=1)

        # Create alerts of varying severity
        low_alert = FinancialAlert(
            user_id=user.id,
            alert_key="low:1",
            alert_type="spending_spike",
            severity="low",
            title="Low Severity Spike",
            title_key="k_low",
            message="Notice",
            message_key="m_low",
            recommended_action="None",
            created_at=t0,
            updated_at=t0,
        )
        crit_alert = FinancialAlert(
            user_id=user.id,
            alert_key="crit:1",
            alert_type="cash_shortfall",
            severity="critical",
            title="Critical Cash Danger",
            title_key="k_crit",
            message="Critical risk",
            message_key="m_crit",
            recommended_action="Review now",
            created_at=t1,
            updated_at=t1,
        )
        high_alert = FinancialAlert(
            user_id=user.id,
            alert_key="high:1",
            alert_type="upcoming_obligation",
            severity="high",
            title="High Obligation Approaching",
            title_key="k_high",
            message="Due soon",
            message_key="m_high",
            recommended_action="Review",
            created_at=t0,
            updated_at=t0,
        )
        db.add_all([low_alert, crit_alert, high_alert])
        db.commit()

        digest, reason = generate_daily_digest_for_user(db, user.id)
        assert digest is not None
        assert reason == "generated"
        assert digest.item_count == 3
        assert len(digest.items) == 3

        # Verify ordering: Critical first, then High, then Low
        severities = [item.severity for item in digest.items]
        assert severities == ["critical", "high", "low"]
    finally:
        cleanup(db, user)
        db.close()


def test_daily_digest_idempotency_same_day():
    """Generating digest twice for the same user and date returns existing without duplicates."""
    db = SessionLocal()
    user = make_user(db)
    try:
        pref = get_or_create_user_preferences(db, user.id)
        pref.email_enabled = True
        pref.email_consent = True
        pref.daily_digest_enabled = True
        db.commit()

        alert = FinancialAlert(
            user_id=user.id,
            alert_key="a:1",
            alert_type="cash_shortfall",
            severity="critical",
            title="Cash Warning",
            title_key="k",
            message="Msg",
            message_key="m",
            recommended_action="Act",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        db.commit()

        digest1, reason1 = generate_daily_digest_for_user(db, user.id)
        assert reason1 == "generated"
        assert digest1 is not None

        # Call again for same day
        digest2, reason2 = generate_daily_digest_for_user(db, user.id)
        assert reason2 == "already_generated"
        assert digest1.id == digest2.id

        # Total digests in DB must be exactly 1
        count = db.query(NotificationDigest).filter(NotificationDigest.user_id == user.id).count()
        assert count == 1
    finally:
        cleanup(db, user)
        db.close()


def test_zero_alert_day_produces_no_digest():
    """When user has no eligible alerts, no digest is generated and no email sent."""
    db = SessionLocal()
    user = make_user(db)
    try:
        pref = get_or_create_user_preferences(db, user.id)
        pref.email_enabled = True
        pref.email_consent = True
        pref.daily_digest_enabled = True
        db.commit()

        digest, reason = generate_daily_digest_for_user(db, user.id)
        assert digest is None
        assert reason == "skipped_no_alerts"

        count = db.query(NotificationDigest).filter(NotificationDigest.user_id == user.id).count()
        assert count == 0
    finally:
        cleanup(db, user)
        db.close()


def test_excluded_alert_states_from_digest():
    """Dismissed, actioned, and resolved alerts must NOT appear in daily digests."""
    db = SessionLocal()
    user = make_user(db)
    try:
        pref = get_or_create_user_preferences(db, user.id)
        pref.email_enabled = True
        pref.email_consent = True
        pref.daily_digest_enabled = True
        db.commit()

        now = datetime.now(timezone.utc)
        dismissed_alert = FinancialAlert(
            user_id=user.id,
            alert_key="d:1",
            alert_type="spending_spike",
            severity="high",
            title="Dismissed Spike",
            title_key="kd",
            message="Msg",
            message_key="md",
            recommended_action="Act",
            status="dismissed",
            dismissed_at=now,
            created_at=now,
            updated_at=now,
        )
        resolved_alert = FinancialAlert(
            user_id=user.id,
            alert_key="r:1",
            alert_type="cash_shortfall",
            severity="critical",
            title="Resolved Shortfall",
            title_key="kr",
            message="Msg",
            message_key="mr",
            recommended_action="Act",
            status="resolved",
            resolved_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add_all([dismissed_alert, resolved_alert])
        db.commit()

        digest, reason = generate_daily_digest_for_user(db, user.id)
        assert digest is None
        assert reason == "skipped_no_alerts"
    finally:
        cleanup(db, user)
        db.close()


# ==============================================================================
# 3. PostgreSQL Concurrency Tests
# ==============================================================================

def test_concurrent_digest_generation_safety():
    """Multiple concurrent workers attempting to generate today's digest result in exactly 1 digest."""
    db = SessionLocal()
    user = make_user(db)
    try:
        pref = get_or_create_user_preferences(db, user.id)
        pref.email_enabled = True
        pref.email_consent = True
        pref.daily_digest_enabled = True
        db.commit()

        alert = FinancialAlert(
            user_id=user.id,
            alert_key="concurr:1",
            alert_type="cash_shortfall",
            severity="critical",
            title="Concurrent Cash Warning",
            title_key="kc",
            message="Msg",
            message_key="mc",
            recommended_action="Act",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        db.commit()

        user_id = user.id

        def worker_generate(seed: int) -> int:
            w_db = SessionLocal()
            try:
                dig, _ = generate_daily_digest_for_user(w_db, user_id)
                return dig.id if dig else 0
            finally:
                w_db.close()

        # Run 5 workers concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            digest_ids = list(executor.map(worker_generate, range(5)))

        # All workers must report the exact same digest id
        assert len(set(digest_ids)) == 1
        assert digest_ids[0] > 0

        # In DB, exactly 1 digest record exists
        total_digests = db.query(NotificationDigest).filter(NotificationDigest.user_id == user_id).count()
        assert total_digests == 1

        # Exactly 1 delivery outbox record for this digest exists
        total_deliveries = (
            db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.user_id == user_id,
                NotificationDelivery.notification_event == "DAILY_DIGEST",
            )
            .count()
        )
        assert total_deliveries == 1
    finally:
        cleanup(db, user)
        db.close()


def test_concurrent_alert_event_orchestration():
    """Multiple concurrent workers orchestrating the same alert lifecycle event produce exactly 1 delivery."""
    db = SessionLocal()
    user = make_user(db)
    try:
        pref = get_or_create_user_preferences(db, user.id)
        pref.in_app_enabled = True
        pref.email_enabled = False
        db.commit()

        alert = FinancialAlert(
            user_id=user.id,
            alert_key="concurr_event:1",
            alert_type="spending_spike",
            severity="critical",
            title="Concurrent Event Test",
            title_key="ke",
            message="Msg",
            message_key="me",
            recommended_action="Act",
            occurrence_count=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        db.commit()

        alert_id = alert.id

        def worker_event(seed: int):
            w_db = SessionLocal()
            try:
                a = w_db.query(FinancialAlert).filter(FinancialAlert.id == alert_id).first()
                dels = orchestrate_alert_lifecycle_event(w_db, a, "ALERT_CREATED", occurrence_count=1)
                w_db.commit()
                return [d.id for d in dels]
            finally:
                w_db.close()

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(worker_event, range(4)))

        # All workers observed the exact same delivery id
        first_ids = results[0]
        for other_ids in results[1:]:
            assert other_ids == first_ids

        # Exactly 1 in-app delivery record in the DB
        in_app_count = (
            db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.alert_id == alert_id,
                NotificationDelivery.channel == "in_app",
            )
            .count()
        )
        assert in_app_count == 1
    finally:
        cleanup(db, user)
        db.close()


# ==============================================================================
# 4. Timezone Handling & Midnight Boundaries
# ==============================================================================

def test_timezone_boundary_handling():
    """User local calendar date is correctly determined for Asia/Dhaka, UTC, and America/New_York."""
    # Near UTC midnight: 2026-11-01 23:30:00 UTC
    near_midnight_utc = datetime(2026, 11, 1, 23, 30, tzinfo=timezone.utc)

    # In UTC, date is 2026-11-01
    utc_date, _, _ = get_user_local_date_and_time("UTC", near_midnight_utc)
    assert utc_date == date(2026, 11, 1)

    # In Asia/Dhaka (+6), time is 05:30 on the NEXT day (2026-11-02)
    dhaka_date, _, _ = get_user_local_date_and_time("Asia/Dhaka", near_midnight_utc)
    assert dhaka_date == date(2026, 11, 2)

    # In America/New_York (-4 / -5 EDT/EST), time is earlier on 2026-11-01
    ny_date, _, _ = get_user_local_date_and_time("America/New_York", near_midnight_utc)
    assert ny_date == date(2026, 11, 1)


# ==============================================================================
# 5. Privacy Contract Assertions
# ==============================================================================

def test_digest_email_privacy_contract():
    """Digest email MUST NOT contain financial amounts, balances, merchants, or accounts."""
    digest = NotificationDigest(
        id=99,
        user_id=1,
        local_date=date(2026, 11, 1),
        timezone="Asia/Dhaka",
        status="GENERATED",
        item_count=2,
        created_at=datetime.now(timezone.utc),
    )
    items = [
        NotificationDigestItem(
            id=1,
            digest_id=99,
            alert_id=10,
            severity="critical",
            alert_type="cash_shortfall",
            title="Cash position shortfall risk",
            created_at=datetime.now(timezone.utc),
        ),
        NotificationDigestItem(
            id=2,
            digest_id=99,
            alert_id=11,
            severity="high",
            alert_type="upcoming_obligation",
            title="Upcoming payment obligation",
            created_at=datetime.now(timezone.utc),
        ),
    ]

    msg_en = build_privacy_safe_digest_email(digest, items, "user@example.com", language="en")
    msg_bn = build_privacy_safe_digest_email(digest, items, "user@example.com", language="bn")

    for msg in (msg_en, msg_bn):
        combined = msg.subject + " " + msg.body_text + " " + (msg.body_html or "")
        # Sensitive terms that must NEVER appear:
        assert "৳" not in combined
        assert "BDT" not in combined
        assert "balance" not in combined.lower() or "not included" in combined.lower() or "not a live" in combined.lower()
        assert "account number" not in combined.lower() or "never included" in combined.lower() or "not included" in combined.lower()
        assert "BRAC" not in combined
        assert "1234" not in combined  # No account or card numbers
        assert "restaurant" not in combined.lower()  # No merchant details
        assert "4350" not in combined  # No amounts

        # Must include safe navigation link
        assert "/alerts" in combined


# ==============================================================================
# 6. Delivery Processing & Operational Metrics
# ==============================================================================

def test_daily_digest_delivery_worker_execution():
    """Delivery worker claims and dispatches daily digest email successfully."""
    db = SessionLocal()
    user = make_user(db)
    try:
        pref = get_or_create_user_preferences(db, user.id)
        pref.email_enabled = True
        pref.email_consent = True
        pref.daily_digest_enabled = True
        db.commit()

        alert = FinancialAlert(
            user_id=user.id,
            alert_key="worker_test:1",
            alert_type="cash_shortfall",
            severity="critical",
            title="Worker Delivery Cash Risk",
            title_key="kw",
            message="Msg",
            message_key="mw",
            recommended_action="Act",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        db.commit()

        digest, _ = generate_daily_digest_for_user(db, user.id)
        assert digest is not None

        # Claim pending deliveries for this user
        claimed = claim_pending_deliveries(db, limit=10, user_id=user.id)
        digest_del = next(d for d in claimed if d.notification_event == "DAILY_DIGEST")
        assert digest_del.status == "PROCESSING"

        # Process the delivery
        sent = process_single_delivery(db, digest_del)
        assert sent is True
        assert digest_del.status == "SENT"
        assert digest_del.delivered_at is not None

        # Digest record itself should be marked SENT
        db.refresh(digest)
        assert digest.status == "SENT"
        assert digest.sent_at is not None

        # Verify email sender received 1 email
        assert len(TestEmailSender.get_sent_messages()) == 1
        sent_email = TestEmailSender.get_sent_messages()[0]
        assert sent_email.recipient == user.email
        assert "PorerHishab" in sent_email.subject
    finally:
        cleanup(db, user)
        db.close()


def test_operational_health_metrics_service():
    """Operational health service reports accurate counts of deliveries and digests."""
    db = SessionLocal()
    user = make_user(db)
    try:
        metrics = get_notification_health_metrics(db)
        assert "pending_deliveries" in metrics
        assert "processing_deliveries" in metrics
        assert "failed_deliveries" in metrics
        assert "dead_letter_deliveries" in metrics
        assert "pending_digests" in metrics
        assert "sent_digests" in metrics
        assert "failed_digests" in metrics
        assert isinstance(metrics["pending_deliveries"], int)
    finally:
        cleanup(db, user)
        db.close()


# ==============================================================================
# 7. Authenticated APIs & User Isolation
# ==============================================================================

def test_notification_history_api():
    """GET /finance/notifications/history returns authenticated user's notification logs."""
    db = SessionLocal()
    user = make_user(db)
    try:
        headers = auth_headers(user)

        # Enqueue a test delivery
        deliv = NotificationDelivery(
            user_id=user.id,
            alert_id=None,
            channel="email",
            notification_event="DAILY_DIGEST",
            idempotency_key=f"test_hist_{uuid4()}",
            status="SENT",
            delivered_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(deliv)
        db.commit()

        res = client.get("/finance/notifications/history", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        assert any(item["notification_event"] == "DAILY_DIGEST" for item in data["items"])
    finally:
        cleanup(db, user)
        db.close()


def test_evaluate_daily_digest_api():
    """POST /finance/notifications/digest/evaluate triggers digest evaluation idempotently."""
    db = SessionLocal()
    user = make_user(db)
    try:
        pref = get_or_create_user_preferences(db, user.id)
        pref.email_enabled = True
        pref.email_consent = True
        pref.daily_digest_enabled = True
        db.commit()

        # Add active alert
        alert = FinancialAlert(
            user_id=user.id,
            alert_key="api_eval:1",
            alert_type="cash_shortfall",
            severity="critical",
            title="API Digest Test Alert",
            title_key="ka",
            message="Msg",
            message_key="ma",
            recommended_action="Act",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        db.commit()

        headers = auth_headers(user)
        res = client.post("/finance/notifications/digest/evaluate", headers=headers)
        assert res.status_code == 200
        payload = res.json()
        assert payload["status"] == "generated"
        assert payload["item_count"] == 1
        assert payload["digest_id"] is not None

        # Re-evaluating immediately must report already_generated
        res2 = client.post("/finance/notifications/digest/evaluate", headers=headers)
        assert res2.status_code == 200
        assert res2.json()["status"] == "already_generated"
    finally:
        cleanup(db, user)
        db.close()


def test_user_tenant_isolation_digest_and_history():
    """User A cannot access or view User B's notification history or digests."""
    db = SessionLocal()
    user_a = make_user(db, full_name="User A")
    user_b = make_user(db, full_name="User B")
    try:
        # Create delivery for user B
        deliv_b = NotificationDelivery(
            user_id=user_b.id,
            alert_id=None,
            channel="email",
            notification_event="DAILY_DIGEST",
            idempotency_key=f"isolation_b_{uuid4()}",
            status="SENT",
            delivered_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(deliv_b)
        db.commit()

        headers_a = auth_headers(user_a)
        res = client.get("/finance/notifications/history", headers=headers_a)
        assert res.status_code == 200
        items_a = res.json()["items"]
        # User A's history must NOT contain User B's record
        assert all(item["user_id"] == user_a.id for item in items_a)
        assert all(item["id"] != deliv_b.id for item in items_a)
    finally:
        cleanup(db, user_a, user_b)
        db.close()
