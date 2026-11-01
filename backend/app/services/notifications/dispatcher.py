"""Notification delivery dispatcher and outbox processing service.

Provides:
- Deterministic idempotency key generation.
- Concurrency-safe delivery enqueueing.
- Row-level claiming with SELECT FOR UPDATE SKIP LOCKED.
- Channel delivery dispatching (in-app, email).
- Bounded retries with exponential/staged backoff.
- Transient vs permanent failure handling and DEAD_LETTER transitions.
- Independent DB session handling for background tasks.
"""
from datetime import datetime, timedelta, timezone
import logging
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.financial_alert import FinancialAlert
from app.models.notification_delivery import NotificationDelivery
from app.models.notification_preference import NotificationPreference
from app.models.user import User
from app.services.notifications.eligibility import (
    EligibilityReason,
    evaluate_eligibility,
)
from app.services.notifications.email_content import build_privacy_safe_alert_email
from app.services.notifications.email_sender import get_email_sender

logger = logging.getLogger(__name__)


def generate_idempotency_key(
    user_id: int,
    alert_id: int,
    channel: str,
    notification_event: str,
) -> str:
    """Generate a deterministic logical idempotency key. Never uses timestamps."""
    return f"usr_{user_id}:alt_{alert_id}:chn_{channel.lower()}:evt_{notification_event.upper()}"


def get_or_create_user_preferences(
    db: Session,
    user_id: int,
) -> NotificationPreference:
    """Retrieve existing user notification preferences or create defaults."""
    pref = (
        db.query(NotificationPreference)
        .filter(NotificationPreference.user_id == user_id)
        .first()
    )
    if pref is None:
        pref = NotificationPreference(user_id=user_id)
        db.add(pref)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            pref = (
                db.query(NotificationPreference)
                .filter(NotificationPreference.user_id == user_id)
                .first()
            )
    return pref


def enqueue_single_delivery(
    db: Session,
    user_id: int,
    alert_id: int,
    channel: str,
    notification_event: str,
    initial_status: str = "PENDING",
    failure_category: str | None = None,
    failure_reason: str | None = None,
    next_attempt_at: datetime | None = None,
) -> NotificationDelivery:
    """Enqueue a single notification delivery outbox item idempotently."""
    channel_norm = channel.lower()
    event_norm = notification_event.upper()
    key = generate_idempotency_key(user_id, alert_id, channel_norm, event_norm)

    # Check for existing delivery under logical identity or idempotency key
    existing = (
        db.query(NotificationDelivery)
        .filter(
            (NotificationDelivery.user_id == user_id)
            & (NotificationDelivery.alert_id == alert_id)
            & (NotificationDelivery.channel == channel_norm)
            & (NotificationDelivery.notification_event == event_norm)
        )
        .first()
    )
    if existing:
        return existing

    delivery = NotificationDelivery(
        user_id=user_id,
        alert_id=alert_id,
        channel=channel_norm,
        notification_event=event_norm,
        idempotency_key=key,
        status=initial_status,
        attempt_count=0,
        max_attempts=settings.NOTIFICATION_MAX_RETRIES,
        next_attempt_at=next_attempt_at,
        failure_category=failure_category,
        failure_reason=failure_reason,
        metadata_={},
    )
    db.add(delivery)
    try:
        db.flush()
        return delivery
    except IntegrityError:
        db.rollback()
        # Another concurrent worker created this exact record; fetch it
        existing = (
            db.query(NotificationDelivery)
            .filter(NotificationDelivery.idempotency_key == key)
            .first()
        )
        if existing:
            return existing
        raise


def enqueue_notifications_for_alert(
    db: Session,
    alert: FinancialAlert,
    notification_event: str,
) -> list[NotificationDelivery]:
    """Evaluate preferences and enqueue notification delivery records for an alert event."""
    if not settings.NOTIFICATION_DELIVERY_ENABLED:
        return []

    pref = get_or_create_user_preferences(db, alert.user_id)
    deliveries: list[NotificationDelivery] = []
    now = datetime.now(timezone.utc)

    # 1. In-app delivery outbox record
    in_app_eligibility = evaluate_eligibility(
        pref,
        channel="in_app",
        alert_severity=alert.severity,
        notification_event=notification_event,
        now_utc=now,
    )
    if in_app_eligibility.is_eligible:
        d = enqueue_single_delivery(
            db,
            user_id=alert.user_id,
            alert_id=alert.id,
            channel="in_app",
            notification_event=notification_event,
            initial_status="PENDING",
        )
        deliveries.append(d)
    else:
        # Create suppressed record for auditability if desired, or skip
        d = enqueue_single_delivery(
            db,
            user_id=alert.user_id,
            alert_id=alert.id,
            channel="in_app",
            notification_event=notification_event,
            initial_status="SUPPRESSED",
            failure_category=in_app_eligibility.reason.value.lower(),
            failure_reason=f"In-app suppressed: {in_app_eligibility.reason.value}",
        )
        deliveries.append(d)

    # 2. Email delivery outbox record
    email_eligibility = evaluate_eligibility(
        pref,
        channel="email",
        alert_severity=alert.severity,
        notification_event=notification_event,
        now_utc=now,
    )
    if email_eligibility.is_eligible:
        d = enqueue_single_delivery(
            db,
            user_id=alert.user_id,
            alert_id=alert.id,
            channel="email",
            notification_event=notification_event,
            initial_status="PENDING",
            next_attempt_at=now,
        )
        deliveries.append(d)
    elif email_eligibility.reason == EligibilityReason.QUIET_HOURS:
        # Deferred for quiet hours
        d = enqueue_single_delivery(
            db,
            user_id=alert.user_id,
            alert_id=alert.id,
            channel="email",
            notification_event=notification_event,
            initial_status="PENDING",
            next_attempt_at=email_eligibility.next_eligible_at,
            failure_reason="Deferred: quiet hours active",
        )
        deliveries.append(d)
    else:
        # Suppressed due to no consent, disabled, or below threshold
        d = enqueue_single_delivery(
            db,
            user_id=alert.user_id,
            alert_id=alert.id,
            channel="email",
            notification_event=notification_event,
            initial_status="SUPPRESSED",
            failure_category=email_eligibility.reason.value.lower(),
            failure_reason=f"Email suppressed: {email_eligibility.reason.value}",
        )
        deliveries.append(d)

    return deliveries


def claim_pending_deliveries(
    db: Session,
    limit: int = 10,
    user_id: int | None = None,
) -> list[NotificationDelivery]:
    """Claim pending or retryable deliveries atomically using row-level locking.

    Uses SELECT FOR UPDATE SKIP LOCKED on PostgreSQL to prevent competing workers
    from attempting or double-incrementing deliveries simultaneously.
    """
    now = datetime.now(timezone.utc)

    # Check dialect for SKIP LOCKED support
    is_postgres = db.bind is not None and db.bind.dialect.name == "postgresql"

    stmt = select(NotificationDelivery).where(
        NotificationDelivery.status.in_(["PENDING", "FAILED"]),
        (NotificationDelivery.next_attempt_at.is_(None))
        | (NotificationDelivery.next_attempt_at <= now),
    )
    if user_id is not None:
        stmt = stmt.where(NotificationDelivery.user_id == user_id)

    stmt = stmt.order_by(NotificationDelivery.id.asc()).limit(limit)

    if is_postgres:
        stmt = stmt.with_for_update(skip_locked=True)

    claimed: list[NotificationDelivery] = db.execute(stmt).scalars().all()

    for item in claimed:
        item.status = "PROCESSING"
        item.last_attempt_at = now
        item.attempt_count += 1

    if claimed:
        db.commit()

    return claimed


def compute_retry_delay(attempt_count: int) -> timedelta:
    """Compute deterministic backoff delay for retries."""
    backoffs = settings.NOTIFICATION_RETRY_BACKOFF_SECONDS
    idx = min(max(0, attempt_count - 1), len(backoffs) - 1)
    return timedelta(seconds=backoffs[idx])


def process_single_delivery(
    db: Session,
    delivery: NotificationDelivery,
) -> bool:
    """Process a single claimed delivery record."""
    now = datetime.now(timezone.utc)
    logger.info(
        "Processing notification delivery id=%s channel=%s event=%s attempt=%s",
        delivery.id,
        delivery.channel,
        delivery.notification_event,
        delivery.attempt_count,
    )

    alert = (
        db.query(FinancialAlert)
        .filter(FinancialAlert.id == delivery.alert_id)
        .first()
    )
    if not alert:
        delivery.status = "DEAD_LETTER"
        delivery.failed_at = now
        delivery.failure_category = "permanent"
        delivery.failure_reason = "Underlying alert not found"
        db.commit()
        return False

    pref = get_or_create_user_preferences(db, delivery.user_id)

    # Re-verify eligibility at delivery time (in case user changed preferences)
    eligibility = evaluate_eligibility(
        pref,
        channel=delivery.channel,
        alert_severity=alert.severity,
        notification_event=delivery.notification_event,
        now_utc=now,
    )

    if not eligibility.is_eligible:
        if eligibility.reason == EligibilityReason.QUIET_HOURS:
            # Reschedule after quiet hours
            delivery.status = "PENDING"
            delivery.next_attempt_at = eligibility.next_eligible_at
            delivery.failure_reason = "Quiet hours active at send time"
            db.commit()
            return False
        else:
            delivery.status = "SUPPRESSED"
            delivery.failure_category = eligibility.reason.value.lower()
            delivery.failure_reason = f"Suppressed: {eligibility.reason.value}"
            db.commit()
            return False

    # Dispatch to channel
    if delivery.channel == "in_app":
        delivery.status = "SENT"
        delivery.delivered_at = now
        delivery.provider = "in_app"
        delivery.failure_category = None
        delivery.failure_reason = None
        db.commit()
        return True

    elif delivery.channel == "email":
        user = db.query(User).filter(User.id == delivery.user_id).first()
        if not user or not user.email:
            delivery.status = "DEAD_LETTER"
            delivery.failed_at = now
            delivery.failure_category = "invalid_recipient"
            delivery.failure_reason = "User email address missing or unavailable"
            db.commit()
            return False

        email_sender = get_email_sender()
        email_msg = build_privacy_safe_alert_email(alert, user.email)
        result = email_sender.send(email_msg)

        if result.success:
            delivery.status = "SENT"
            delivery.delivered_at = now
            delivery.provider = result.provider
            delivery.failure_category = None
            delivery.failure_reason = None
            db.commit()
            return True
        else:
            delivery.provider = result.provider
            delivery.failure_reason = result.error_message
            delivery.failure_category = result.failure_category

            # Classify transient vs permanent retry
            if result.is_transient and delivery.attempt_count < delivery.max_attempts:
                delivery.status = "FAILED"
                delivery.next_attempt_at = now + compute_retry_delay(delivery.attempt_count)
            else:
                delivery.status = "DEAD_LETTER"
                delivery.failed_at = now

            db.commit()
            return False

    else:
        delivery.status = "DEAD_LETTER"
        delivery.failed_at = now
        delivery.failure_category = "permanent"
        delivery.failure_reason = f"Unsupported channel: {delivery.channel}"
        db.commit()
        return False


def process_delivery_by_id(delivery_id: int) -> bool:
    """Worker task helper that creates an independent database session."""
    db: Session = SessionLocal()
    try:
        delivery = (
            db.query(NotificationDelivery)
            .filter(NotificationDelivery.id == delivery_id)
            .first()
        )
        if not delivery:
            return False

        # Claim if not already processing
        if delivery.status in ("PENDING", "FAILED"):
            delivery.status = "PROCESSING"
            delivery.last_attempt_at = datetime.now(timezone.utc)
            delivery.attempt_count += 1
            db.commit()

        return process_single_delivery(db, delivery)
    finally:
        db.close()


def process_claimed_deliveries(
    db: Session,
    claimed: list[NotificationDelivery],
) -> int:
    """Process a list of already-claimed deliveries."""
    sent_count = 0
    for delivery in claimed:
        if process_single_delivery(db, delivery):
            sent_count += 1
    return sent_count


def dispatch_pending_user_deliveries(user_id: int) -> int:
    """Worker task that dispatches pending notifications for a specific user using its own session."""
    db: Session = SessionLocal()
    try:
        claimed = claim_pending_deliveries(db, limit=20, user_id=user_id)
        return process_claimed_deliveries(db, claimed)
    except Exception as e:
        logger.error("Error processing pending user deliveries for user_id=%s: %s", user_id, e)
        return 0
    finally:
        db.close()
