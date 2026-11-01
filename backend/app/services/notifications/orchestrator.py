"""Domain notification event orchestrator.

Coordinates lifecycle events from the authoritative financial alert engine (AI-15L)
into downstream notification outbox records and digest candidates (AI-15N).

Rules:
- Never recalculates financial metrics or alters financial alert records.
- Deterministic event mapping: ALERT_CREATED, ALERT_ESCALATED, ALERT_RECURRED.
- Unchanged evaluations produce no events.
- Database-enforced idempotency incorporating user, alert, event, channel, and occurrence.
- Immediate delivery vs Daily digest candidates based on user preferences.
- Critical safety alerts bypass immediate disabling to guarantee prompt delivery.
"""
from datetime import datetime, timezone
import logging
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.financial_alert import FinancialAlert
from app.models.notification_delivery import NotificationDelivery
from app.services.notifications.dispatcher import (
    enqueue_single_delivery,
    get_or_create_user_preferences,
)
from app.services.notifications.eligibility import (
    EligibilityReason,
    evaluate_eligibility,
)

logger = logging.getLogger(__name__)

SUPPORTED_LIFECYCLE_EVENTS = {"ALERT_CREATED", "ALERT_ESCALATED", "ALERT_RECURRED"}


def orchestrate_alert_lifecycle_event(
    db: Session,
    alert: FinancialAlert,
    event_type: str,
    occurrence_count: int | None = None,
) -> list[NotificationDelivery]:
    """Orchestrate notification deliveries for a single alert lifecycle event.

    Determines immediate vs digest handling based on user preferences and alert severity.
    """
    if not settings.NOTIFICATION_DELIVERY_ENABLED:
        logger.info("Notification delivery is disabled by configuration; skipping event %s", event_type)
        return []

    event_norm = event_type.upper()
    if event_norm not in SUPPORTED_LIFECYCLE_EVENTS:
        raise ValueError(f"Unsupported alert lifecycle event: {event_type}")

    occ_count = occurrence_count if occurrence_count is not None else alert.occurrence_count
    pref = get_or_create_user_preferences(db, alert.user_id)
    deliveries: list[NotificationDelivery] = []
    now = datetime.now(timezone.utc)
    is_critical = alert.severity.lower() == "critical"

    # 1. In-app delivery
    in_app_eligibility = evaluate_eligibility(
        pref,
        channel="in_app",
        alert_severity=alert.severity,
        notification_event=event_norm,
        now_utc=now,
    )
    if in_app_eligibility.is_eligible:
        d = enqueue_single_delivery(
            db,
            user_id=alert.user_id,
            alert_id=alert.id,
            channel="in_app",
            notification_event=event_norm,
            occurrence_count=occ_count,
            initial_status="PENDING",
        )
        deliveries.append(d)
    else:
        d = enqueue_single_delivery(
            db,
            user_id=alert.user_id,
            alert_id=alert.id,
            channel="in_app",
            notification_event=event_norm,
            occurrence_count=occ_count,
            initial_status="SUPPRESSED",
            failure_category=in_app_eligibility.reason.value.lower(),
            failure_reason=f"In-app suppressed: {in_app_eligibility.reason.value}",
        )
        deliveries.append(d)

    # 2. Email delivery (Immediate evaluation)
    # If user has immediate alerts enabled OR if alert is CRITICAL:
    email_eligibility = evaluate_eligibility(
        pref,
        channel="email",
        alert_severity=alert.severity,
        notification_event=event_norm,
        now_utc=now,
    )

    if email_eligibility.is_eligible:
        d = enqueue_single_delivery(
            db,
            user_id=alert.user_id,
            alert_id=alert.id,
            channel="email",
            notification_event=event_norm,
            occurrence_count=occ_count,
            initial_status="PENDING",
            next_attempt_at=now,
        )
        deliveries.append(d)
    elif email_eligibility.reason == EligibilityReason.QUIET_HOURS:
        d = enqueue_single_delivery(
            db,
            user_id=alert.user_id,
            alert_id=alert.id,
            channel="email",
            notification_event=event_norm,
            occurrence_count=occ_count,
            initial_status="PENDING",
            next_attempt_at=email_eligibility.next_eligible_at,
            failure_reason="Deferred: quiet hours active",
        )
        deliveries.append(d)
    else:
        d = enqueue_single_delivery(
            db,
            user_id=alert.user_id,
            alert_id=alert.id,
            channel="email",
            notification_event=event_norm,
            occurrence_count=occ_count,
            initial_status="SUPPRESSED",
            failure_category=email_eligibility.reason.value.lower(),
            failure_reason=f"Email suppressed: {email_eligibility.reason.value}",
        )
        deliveries.append(d)

    logger.info(
        "Orchestrated %d deliveries for user_id=%s alert_id=%s event=%s severity=%s",
        len(deliveries),
        alert.user_id,
        alert.id,
        event_norm,
        alert.severity,
    )
    return deliveries

