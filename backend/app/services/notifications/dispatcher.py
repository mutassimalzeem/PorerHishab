"""Notification delivery dispatcher and outbox processing service.

Provides:
- Deterministic idempotency key generation.
- Concurrency-safe delivery enqueueing.
- Row-level claiming with SELECT FOR UPDATE SKIP LOCKED.
- Channel delivery dispatching (in-app, email, daily digest).
- Bounded retries with exponential/staged backoff.
- Transient vs permanent failure handling and DEAD_LETTER transitions.
- Independent DB session handling for background tasks.
"""
from datetime import datetime, timedelta, timezone
import logging
from hashlib import sha256
import random
from uuid import uuid4
from sqlalchemy import select, or_, and_
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
    alert_id: int | None,
    channel: str,
    notification_event: str,
    occurrence_count: int | None = None,
    digest_id: int | None = None,
) -> str:
    """Generate a deterministic logical idempotency key. Never uses timestamps."""
    channel_norm = channel.lower()
    event_norm = notification_event.upper()
    if digest_id is not None:
        return f"usr_{user_id}:digest_{digest_id}:chn_{channel_norm}:evt_{event_norm}"
    if occurrence_count is not None and occurrence_count > 1:
        return f"usr_{user_id}:alt_{alert_id}:chn_{channel_norm}:evt_{event_norm}:occ_{occurrence_count}"
    return f"usr_{user_id}:alt_{alert_id}:chn_{channel_norm}:evt_{event_norm}"


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
        try:
            with db.begin_nested():
                db.add(pref)
                db.flush()
        except IntegrityError:
            pref = (
                db.query(NotificationPreference)
                .filter(NotificationPreference.user_id == user_id)
                .first()
            )
    return pref


def enqueue_single_delivery(
    db: Session,
    user_id: int,
    alert_id: int | None,
    channel: str,
    notification_event: str,
    initial_status: str = "PENDING",
    failure_category: str | None = None,
    failure_reason: str | None = None,
    next_attempt_at: datetime | None = None,
    occurrence_count: int = 1,
    digest_id: int | None = None,
) -> NotificationDelivery:
    """Enqueue a single notification delivery outbox item idempotently."""
    channel_norm = channel.lower()
    event_norm = notification_event.upper()
    key = generate_idempotency_key(
        user_id,
        alert_id,
        channel_norm,
        event_norm,
        occurrence_count=occurrence_count,
        digest_id=digest_id,
    )

    # Check for existing delivery under logical identity or idempotency key
    query = db.query(NotificationDelivery).filter(
        NotificationDelivery.user_id == user_id,
        NotificationDelivery.channel == channel_norm,
        NotificationDelivery.notification_event == event_norm,
    )
    if digest_id is not None:
        query = query.filter(NotificationDelivery.digest_id == digest_id)
    else:
        query = query.filter(
            NotificationDelivery.alert_id == alert_id,
            NotificationDelivery.occurrence_count == occurrence_count,
        )

    existing = query.first()
    if not existing:
        existing = (
            db.query(NotificationDelivery)
            .filter(NotificationDelivery.idempotency_key == key)
            .first()
        )
    if existing:
        return existing

    delivery = NotificationDelivery(
        user_id=user_id,
        alert_id=alert_id,
        digest_id=digest_id,
        channel=channel_norm,
        notification_event=event_norm,
        occurrence_count=occurrence_count,
        idempotency_key=key,
        status=initial_status,
        attempt_count=0,
        max_attempts=settings.NOTIFICATION_MAX_RETRIES,
        next_attempt_at=next_attempt_at,
        failure_category=failure_category,
        failure_reason=failure_reason,
        metadata_={},
    )
    try:
        with db.begin_nested():
            db.add(delivery)
            db.flush()
        return delivery
    except IntegrityError:
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
    from app.services.notifications.orchestrator import orchestrate_alert_lifecycle_event
    return orchestrate_alert_lifecycle_event(db, alert, notification_event)


def claim_pending_deliveries(
    db: Session,
    limit: int = 10,
    user_id: int | None = None,
    delivery_id: int | None = None,
) -> list[NotificationDelivery]:
    """Commit a bounded claim before any provider I/O; PostgreSQL workers skip locks."""
    if not settings.NOTIFICATION_DELIVERY_ENABLED:
        return []
    now = datetime.now(timezone.utc)
    due = and_(
        NotificationDelivery.status.in_(["PENDING", "FAILED"]),
        or_(NotificationDelivery.next_attempt_at.is_(None),
            NotificationDelivery.next_attempt_at <= now),
    )
    abandoned = and_(
        NotificationDelivery.status == "PROCESSING",
        or_(NotificationDelivery.lease_expires_at.is_(None),
            NotificationDelivery.lease_expires_at <= now),
    )
    stmt = select(NotificationDelivery).where(or_(due, abandoned))
    if user_id is not None:
        stmt = stmt.where(NotificationDelivery.user_id == user_id)
    if delivery_id is not None:
        stmt = stmt.where(NotificationDelivery.id == delivery_id)
    stmt = stmt.order_by(NotificationDelivery.id).limit(max(1, min(limit, 100)))
    if db.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    rows = db.execute(stmt.execution_options(populate_existing=True)).scalars().all()
    claimed = []
    for item in rows:
        if item.attempt_count >= item.max_attempts:
            item.status = "DEAD_LETTER"
            item.failed_at = now
            item.failure_category = "permanent"
            item.failure_reason = "Delivery attempt limit exhausted; prior outcome may be unknown"
            item.claim_token = None
            item.lease_expires_at = None
            _update_digest(db, item, now)
            continue
        item.status = "PROCESSING"
        item.claim_token = str(uuid4())
        item._worker_token = item.claim_token
        item.lease_expires_at = now + timedelta(seconds=settings.NOTIFICATION_LEASE_SECONDS)
        item.last_attempt_at = now
        item.attempt_count += 1
        claimed.append(item)
    db.commit()
    # Load all values before caller starts processing other items with this session.
    for item in claimed:
        db.refresh(item)
    db.commit()
    return claimed


def compute_retry_delay(attempt_count: int, retry_after_seconds: float | None = None,
                        *, jitter: bool = False) -> timedelta:
    """Exponential delay with optional legacy staged floors, cap, jitter and Retry-After."""
    backoffs = settings.NOTIFICATION_RETRY_BACKOFF_SECONDS or [60]
    exponent = min(max(0, attempt_count - 1), 30)
    floor = backoffs[min(exponent, len(backoffs) - 1)]
    delay = max(floor, max(1, backoffs[0]) * (2 ** exponent))
    if jitter:
        delay += random.uniform(0, max(0, settings.NOTIFICATION_RETRY_JITTER_SECONDS))
    delay = min(max(0, settings.NOTIFICATION_RETRY_MAX_DELAY_SECONDS), delay)
    # A provider's minimum wait takes precedence over the local backoff cap.
    return timedelta(seconds=max(delay, retry_after_seconds or 0))


def _update_digest(db: Session, delivery: NotificationDelivery, now: datetime) -> None:
    if delivery.digest_id is None:
        return
    from app.models.notification_digest import NotificationDigest
    digest = db.query(NotificationDigest).filter_by(
        id=delivery.digest_id, user_id=delivery.user_id).first()
    if digest is None:
        return
    if delivery.status == "SENT":
        digest.status, digest.sent_at, digest.failure_reason = "SENT", now, None
    elif delivery.status in ("DEAD_LETTER", "SUPPRESSED"):
        digest.status, digest.failed_at = "FAILED", now
        digest.failure_reason = delivery.failure_reason
    else:
        digest.status = "PENDING"


def _prepare_message(db: Session, delivery: NotificationDelivery, now: datetime):
    """Return a privacy-safe message or a suppression/failure without provider I/O."""
    from app.services.notifications.eligibility import calculate_quiet_hours_window, SEVERITY_ORDER
    from app.models.notification_digest import NotificationDigest
    from app.services.notifications.email_content import build_privacy_safe_digest_email

    pref = get_or_create_user_preferences(db, delivery.user_id)
    owner = db.get(User, delivery.user_id)
    if delivery.channel == "email" and (owner is None or not owner.email_verified):
        return None, "SUPPRESSED", "email_not_verified", None
    if delivery.digest_id is not None:
        digest = db.query(NotificationDigest).filter_by(
            id=delivery.digest_id, user_id=delivery.user_id).first()
        if digest is None:
            return None, "DEAD_LETTER", "permanent", None
        if (delivery.channel != "email" or not pref.email_enabled or not pref.email_consent
                or not pref.daily_digest_enabled or pref.frequency_mode == "off"):
            return None, "SUPPRESSED", "no_consent", None
        # Do not send a stale summary after its source alerts cease to be eligible.
        sources = [
            db.query(FinancialAlert).filter_by(
                id=item.alert_id, user_id=delivery.user_id, status="active").first()
            for item in digest.items
        ]
        minimum = SEVERITY_ORDER.get((pref.email_min_severity or "warning").lower(), 30)
        if not sources or any(
            alert is None or SEVERITY_ORDER.get(alert.severity.lower(), 10) < minimum
            for alert in sources
        ):
            return None, "SUPPRESSED", "permanent", None
        if pref.quiet_hours_enabled:
            quiet, until = calculate_quiet_hours_window(
                now, pref.quiet_hours_start, pref.quiet_hours_end, pref.timezone)
            if quiet:
                return None, "PENDING", "quiet_hours", until
        user = db.query(User).filter_by(id=delivery.user_id).first()
        if user is None or not user.email:
            return None, "DEAD_LETTER", "invalid_recipient", None
        return build_privacy_safe_digest_email(digest, digest.items, user.email), None, None, None

    alert = db.query(FinancialAlert).filter_by(
        id=delivery.alert_id, user_id=delivery.user_id).first()
    if alert is None:
        return None, "DEAD_LETTER", "permanent", None
    if alert.status != "active":
        return None, "SUPPRESSED", "permanent", None
    eligibility = evaluate_eligibility(
        pref, user=owner, channel=delivery.channel, alert_severity=alert.severity,
        notification_event=delivery.notification_event, now_utc=now)
    if not eligibility.is_eligible:
        if eligibility.reason == EligibilityReason.QUIET_HOURS:
            return None, "PENDING", "quiet_hours", eligibility.next_eligible_at
        return None, "SUPPRESSED", "channel_disabled", None
    if delivery.channel == "in_app":
        return None, "SENT", None, None
    user = db.query(User).filter_by(id=delivery.user_id).first()
    if user is None or not user.email:
        return None, "DEAD_LETTER", "invalid_recipient", None
    return build_privacy_safe_alert_email(alert, user.email), None, None, None


def process_single_delivery(db: Session, delivery: NotificationDelivery) -> bool:
    """Only a live claim can send and finalize; never hold a transaction over I/O."""
    from app.services.notifications.email_sender import EmailSendResult
    identity, token = delivery.id, getattr(delivery, "_worker_token", None)
    if delivery.status != "PROCESSING" or not token:
        return False
    now = datetime.now(timezone.utc)
    current = db.query(NotificationDelivery).filter(
        NotificationDelivery.id == identity, NotificationDelivery.claim_token == token,
        NotificationDelivery.status == "PROCESSING",
        NotificationDelivery.lease_expires_at > now,
    ).populate_existing().first()
    if current is None:
        db.rollback()
        return False
    message, status, category, next_at = _prepare_message(db, current, now)
    key = current.idempotency_key
    db.commit()
    # commit expires ORM objects. Do not access them here: it would start a transaction.
    result = None
    if message is not None:
        message.headers["Message-ID"] = "<" + sha256(key.encode()).hexdigest() + "@notifications.porerhishab>"
        message.headers["X-Idempotency-Key"] = key
        try:
            result = get_email_sender().send(message)
        except (TimeoutError, ConnectionError, OSError):
            result = EmailSendResult(False, "adapter", is_transient=True, failure_category="transient")
        except Exception:
            # Unknown adapter errors are retained as safe failure categories, never raw text.
            logger.error("notification_provider_exception delivery_id=%s", identity)
            result = EmailSendResult(False, "adapter", is_transient=False, failure_category="provider_error")

    now = datetime.now(timezone.utc)
    # Lock only the short completion transaction, and fence against reclaimed/expired workers.
    current = db.execute(select(NotificationDelivery).where(
        NotificationDelivery.id == identity, NotificationDelivery.claim_token == token,
        NotificationDelivery.status == "PROCESSING",
        NotificationDelivery.lease_expires_at > now,
    ).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if current is None or current.lease_expires_at.replace(tzinfo=timezone.utc) <= now:
        db.rollback()
        return False
    if result is not None:
        current.provider = result.provider if result.provider in ("test", "smtp", "adapter") else "adapter"
        category = result.failure_category if result.failure_category in (
            "transient", "permanent", "invalid_recipient", "rate_limited", "provider_error"
        ) else "provider_error"
        if result.success:
            status, category = "SENT", None
        elif result.is_transient and current.attempt_count < current.max_attempts:
            status = "FAILED"
            next_at = now + compute_retry_delay(
                current.attempt_count, result.retry_after_seconds, jitter=True)
        else:
            status = "DEAD_LETTER"
    current.status = status
    current.next_attempt_at = next_at
    current.failure_category = category
    current.failure_reason = None if category is None else "Notification delivery: " + category
    current.claim_token = None
    current.lease_expires_at = None
    if status == "SENT":
        current.delivered_at = now
        if message is None:
            current.provider = "in_app"
    elif status == "DEAD_LETTER":
        current.failed_at = now
    elif status in ("PENDING", "SUPPRESSED"):
        # Eligibility checks are not provider attempts.
        current.attempt_count = max(0, current.attempt_count - 1)
    _update_digest(db, current, now)
    db.commit()
    db.refresh(delivery)
    db.commit()
    logger.info("notification_delivery_result delivery_id=%s status=%s", identity, status)
    return status == "SENT"


def process_delivery_by_id(delivery_id: int) -> bool:
    """Use the same atomic eligibility/claim path as periodic and request workers."""
    with SessionLocal() as db:
        rows = claim_pending_deliveries(db, limit=1, delivery_id=delivery_id)
        return bool(rows and process_single_delivery(db, rows[0]))


def process_claimed_deliveries(db: Session, claimed: list[NotificationDelivery]) -> int:
    return sum(process_single_delivery(db, delivery) for delivery in claimed)


def dispatch_pending_user_deliveries(user_id: int) -> int:
    """Optional request wakeup; durable periodic worker is the recovery path."""
    with SessionLocal() as db:
        try:
            claimed = claim_pending_deliveries(db, limit=20, user_id=user_id)
            return process_claimed_deliveries(db, claimed)
        except Exception:
            db.rollback()
            logger.error("notification_dispatch_failed user_id=%s", user_id)
            raise
