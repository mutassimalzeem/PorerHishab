"""Operational visibility and health metrics for notification delivery and digests."""
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.notification_delivery import NotificationDelivery
from app.models.notification_digest import NotificationDigest


def get_notification_health_metrics(db: Session) -> dict[str, int | float | None]:
    """Report aggregate operational health metrics for notification delivery and digests."""
    now = datetime.now(timezone.utc)

    # Deliveries by status
    pending_deliveries = (
        db.query(func.count(NotificationDelivery.id))
        .filter(NotificationDelivery.status == "PENDING")
        .scalar()
        or 0
    )
    processing_deliveries = (
        db.query(func.count(NotificationDelivery.id))
        .filter(NotificationDelivery.status == "PROCESSING")
        .scalar()
        or 0
    )
    failed_deliveries = (
        db.query(func.count(NotificationDelivery.id))
        .filter(NotificationDelivery.status == "FAILED")
        .scalar()
        or 0
    )
    dead_letter_deliveries = (
        db.query(func.count(NotificationDelivery.id))
        .filter(NotificationDelivery.status == "DEAD_LETTER")
        .scalar()
        or 0
    )

    # Digests by status
    pending_digests = (
        db.query(func.count(NotificationDigest.id))
        .filter(NotificationDigest.status.in_(["PENDING", "GENERATED"]))
        .scalar()
        or 0
    )
    sent_digests = (
        db.query(func.count(NotificationDigest.id))
        .filter(NotificationDigest.status == "SENT")
        .scalar()
        or 0
    )
    failed_digests = (
        db.query(func.count(NotificationDigest.id))
        .filter(NotificationDigest.status == "FAILED")
        .scalar()
        or 0
    )

    # Oldest pending delivery age in seconds
    oldest_pending = (
        db.query(NotificationDelivery.created_at)
        .filter(NotificationDelivery.status == "PENDING")
        .order_by(NotificationDelivery.created_at.asc())
        .first()
    )
    oldest_pending_age_seconds: float | None = None
    if oldest_pending and oldest_pending[0]:
        oldest_pending_age_seconds = (now - oldest_pending[0].replace(tzinfo=timezone.utc)).total_seconds()

    return {
        "pending_deliveries": pending_deliveries,
        "processing_deliveries": processing_deliveries,
        "failed_deliveries": failed_deliveries,
        "dead_letter_deliveries": dead_letter_deliveries,
        "pending_digests": pending_digests,
        "sent_digests": sent_digests,
        "failed_digests": failed_digests,
        "oldest_pending_delivery_age_seconds": oldest_pending_age_seconds,
    }
