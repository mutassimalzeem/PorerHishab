"""Daily digest engine for consolidating proactive financial alerts.

Aggregates active, un-digestified financial alerts for eligible users into a single
privacy-safe daily email notification.

Guarantees:
- Deterministic, database-enforced idempotency: at most one digest per user per local date.
- Timezone-aware date boundaries (never relies on server UTC midnight).
- Zero LLM usage. Pure deterministic aggregation and template rendering.
- Privacy-safe: zero balances, amounts, merchants, or financial evidence in emails.
- Safe under concurrent worker execution via PostgreSQL row-level locks and unique constraints.
- No-alert days produce no email digests.
- Dismissed, actioned, and resolved alerts are excluded.
- Non-critical alerts notified immediately today are suppressed from duplicate digest.
- Critical alerts may reappear in the daily digest as high-priority reminders.
"""
from datetime import date, datetime, time, timezone
import logging
from typing import Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.financial_alert import FinancialAlert
from app.models.notification_delivery import NotificationDelivery
from app.models.user import User
from app.models.notification_digest import NotificationDigest, NotificationDigestItem
from app.models.notification_preference import NotificationPreference
from app.services.notifications.dispatcher import (
    enqueue_single_delivery,
    get_or_create_user_preferences,
)
from app.services.notifications.eligibility import SEVERITY_ORDER, parse_hh_mm

logger = logging.getLogger(__name__)

DIGEST_SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


def get_user_local_date_and_time(
    tz_name: str,
    now_utc: datetime | None = None,
) -> tuple[date, time, datetime]:
    """Deterministically convert current UTC time to user local date, time, and datetime."""
    now = now_utc or datetime.now(timezone.utc)
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("Asia/Dhaka")

    local_dt = now.astimezone(tz)
    return local_dt.date(), local_dt.time(), local_dt


def select_eligible_alerts_for_digest(
    db: Session,
    user_id: int,
    pref: NotificationPreference,
    local_date: date,
) -> list[FinancialAlert]:
    """Select alerts eligible for inclusion in the user's daily digest.

    Inclusion rules:
    - Owned by user_id and status is active.
    - Dismissed, actioned, and resolved alerts are strictly excluded.
    - Alert severity >= preference.email_min_severity.
    - Alert has not already been included in another daily digest for this user.
    - If an immediate email was already sent today for this alert:
      - Critical alerts may still be included as a daily safety reminder.
      - Non-critical alerts are excluded to avoid duplicate communication.
    """
    min_sev = (pref.email_min_severity or "warning").lower()
    min_sev_rank = SEVERITY_ORDER.get(min_sev, 10)

    # 1. Fetch all active alerts for this user
    active_alerts = (
        db.query(FinancialAlert)
        .filter(
            FinancialAlert.user_id == user_id,
            FinancialAlert.status == "active",
        )
        .all()
    )

    if not active_alerts:
        return []

    # 2. Find alert IDs already included in any previous digest for this user
    previously_digested_alert_ids = {
        row[0]
        for row in (
            db.query(NotificationDigestItem.alert_id)
            .join(NotificationDigest, NotificationDigest.id == NotificationDigestItem.digest_id)
            .filter(NotificationDigest.user_id == user_id)
            .all()
        )
    }

    # 3. Find alert IDs that had immediate emails sent today
    # Compute local start-of-day in UTC
    try:
        tz = ZoneInfo(pref.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Dhaka")

    local_start_of_day = datetime.combine(local_date, time(0, 0), tzinfo=tz).astimezone(timezone.utc)

    sent_today_alert_ids = {
        row[0]
        for row in (
            db.query(NotificationDelivery.alert_id)
            .filter(
                NotificationDelivery.user_id == user_id,
                NotificationDelivery.channel == "email",
                NotificationDelivery.status == "SENT",
                NotificationDelivery.alert_id.isnot(None),
                NotificationDelivery.delivered_at >= local_start_of_day,
            )
            .all()
        )
    }

    eligible: list[FinancialAlert] = []
    for alert in active_alerts:
        sev = alert.severity.lower()
        sev_rank = SEVERITY_ORDER.get(sev, 10)

        # Severity threshold check
        if sev_rank < min_sev_rank:
            continue

        # Prevent duplicate digest inclusion
        if alert.id in previously_digested_alert_ids:
            continue

        # Immediate email check
        is_critical = sev == "critical"
        if alert.id in sent_today_alert_ids and not is_critical:
            # Non-critical alert was already emailed today; suppress to avoid spam
            continue

        eligible.append(alert)

    # Sort deterministically: Critical > High > Medium > Low > Info, then created_at asc
    eligible.sort(
        key=lambda a: (
            DIGEST_SEVERITY_ORDER.get(a.severity.lower(), 99),
            a.created_at or datetime.min.replace(tzinfo=timezone.utc),
        )
    )

    return eligible


def generate_daily_digest_for_user(
    db: Session,
    user_id: int,
    *,
    as_of_date: date | None = None,
    force: bool = False,
    now_utc: datetime | None = None,
) -> tuple[NotificationDigest | None, str]:
    """Generate and enqueue a single daily digest for a user idempotently.

    Returns (digest, reason_str).
    """
    # Serialize the existing-digest check and alert eligibility read. Otherwise
    # a concurrent commit can make alerts disappear between the two reads and
    # incorrectly return skipped_no_alerts instead of the persisted digest.
    owner = db.query(User).filter(User.id == user_id).with_for_update().one()
    if not owner.email_verified:
        return None, "skipped_unverified_email"
    pref = get_or_create_user_preferences(db, user_id)
    now = now_utc or datetime.now(timezone.utc)

    # Preference validations
    if not pref.daily_digest_enabled and not force:
        return None, "skipped_disabled"

    if not pref.email_consent or not pref.email_enabled:
        return None, "skipped_no_consent"

    local_date, _, _ = get_user_local_date_and_time(pref.timezone, now)
    target_date = as_of_date or local_date

    # Database-level uniqueness check for the user's local date
    existing = (
        db.query(NotificationDigest)
        .filter(
            NotificationDigest.user_id == user_id,
            NotificationDigest.local_date == target_date,
        )
        .first()
    )
    if existing:
        return existing, "already_generated"

    # Select eligible alerts
    alerts = select_eligible_alerts_for_digest(db, user_id, pref, target_date)
    if not alerts:
        return None, "skipped_no_alerts"

    # Create persistent digest record
    digest = NotificationDigest(
        user_id=user_id,
        local_date=target_date,
        timezone=pref.timezone,
        status="GENERATED",
        item_count=len(alerts),
        created_at=now,
        metadata_={"generated_at": now.isoformat()},
    )
    db.add(digest)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        # Another concurrent worker created this exact date digest
        existing = (
            db.query(NotificationDigest)
            .filter(
                NotificationDigest.user_id == user_id,
                NotificationDigest.local_date == target_date,
            )
            .first()
        )
        if existing:
            return existing, "already_generated"
        raise

    # Add digest items
    for alert in alerts:
        item = NotificationDigestItem(
            digest_id=digest.id,
            alert_id=alert.id,
            severity=alert.severity,
            alert_type=alert.alert_type,
            title=alert.title,
            created_at=now,
        )
        db.add(item)

    # Enqueue email delivery outbox record for the digest
    enqueue_single_delivery(
        db,
        user_id=user_id,
        alert_id=None,
        digest_id=digest.id,
        channel="email",
        notification_event="DAILY_DIGEST",
        initial_status="PENDING",
        next_attempt_at=now,
    )

    db.commit()
    db.refresh(digest)

    logger.info(
        "Generated daily digest id=%s user_id=%s date=%s items=%s",
        digest.id,
        user_id,
        target_date,
        len(alerts),
    )
    return digest, "generated"


def generate_daily_digests(
    db: Session,
    now_utc: datetime | None = None,
) -> list[NotificationDigest]:
    """Find all users eligible for daily digest dispatch and generate digests."""
    now = now_utc or datetime.now(timezone.utc)

    # Find users with daily digest and email enabled with consent
    eligible_prefs = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.daily_digest_enabled.is_(True),
            NotificationPreference.email_enabled.is_(True),
            NotificationPreference.email_consent.is_(True),
        )
        .all()
    )

    generated: list[NotificationDigest] = []
    for pref in eligible_prefs:
        local_date, local_time, _ = get_user_local_date_and_time(pref.timezone, now)
        digest_time = parse_hh_mm(pref.daily_digest_time, time(20, 0))

        # Check if user's local time has reached their configured digest time
        if local_time >= digest_time:
            digest, reason = generate_daily_digest_for_user(
                db,
                pref.user_id,
                as_of_date=local_date,
                now_utc=now,
            )
            if digest and reason == "generated":
                generated.append(digest)

    return generated
