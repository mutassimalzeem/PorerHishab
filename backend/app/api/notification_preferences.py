"""Authenticated API endpoints for user notification preferences, delivery history, and daily digest."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.notification_delivery import NotificationDelivery
from app.models.notification_digest import NotificationDigest
from app.models.notification_preference import NotificationPreference
from app.models.user import User
from app.schemas.notification_delivery import (
    NotificationDeliveryListResponse,
    NotificationDeliveryResponse,
    NotificationHistoryItemResponse,
    NotificationHistoryListResponse,
)
from app.schemas.notification_digest import (
    DigestEvaluationResponse,
    NotificationDigestResponse,
)
from app.schemas.notification_preferences import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)
from app.services.notifications.digest_engine import (
    generate_daily_digest_for_user,
    get_user_local_date_and_time,
)
from app.services.notifications.dispatcher import (
    dispatch_pending_user_deliveries,
    get_or_create_user_preferences,
)

router = APIRouter(
    prefix="/finance",
    tags=["notification preferences and digests"],
)


@router.get(
    "/notification-preferences",
    response_model=NotificationPreferenceResponse,
)
def get_user_notification_preferences(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPreferenceResponse:
    """Retrieve owner-scoped notification preferences or initialize defaults."""
    pref = get_or_create_user_preferences(db, current.id)
    return NotificationPreferenceResponse.model_validate(pref)


@router.put(
    "/notification-preferences",
    response_model=NotificationPreferenceResponse,
)
def update_user_notification_preferences(
    payload: NotificationPreferenceUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPreferenceResponse:
    """Update owner-scoped notification preferences."""
    pref = get_or_create_user_preferences(db, current.id)
    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("email_enabled") or update_data.get("email_consent"):
        if not current.email_verified:
            raise HTTPException(
                status_code=403,
                detail="Verify your email address before enabling email notifications.",
            )

    if "email_consent" in update_data:
        if update_data["email_consent"] and not pref.email_consent:
            pref.email_consent_at = datetime.now(timezone.utc)
        elif not update_data["email_consent"] and pref.email_consent:
            pref.email_consent_at = None

    for field, val in update_data.items():
        setattr(pref, field, val)

    pref.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pref)
    return NotificationPreferenceResponse.model_validate(pref)


@router.get(
    "/notification-deliveries",
    response_model=NotificationDeliveryListResponse,
)
def get_user_notification_deliveries(
    channel: Literal["in_app", "email"] | None = Query(default=None),
    status: Literal["PENDING", "PROCESSING", "SENT", "FAILED", "DEAD_LETTER", "SUPPRESSED"] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationDeliveryListResponse:
    """Retrieve owner-scoped notification delivery history with pagination."""
    query = db.query(NotificationDelivery).filter(
        NotificationDelivery.user_id == current.id
    )

    if channel is not None:
        query = query.filter(NotificationDelivery.channel == channel)
    if status is not None:
        query = query.filter(NotificationDelivery.status == status)

    total = query.count()
    items = (
        query.order_by(
            NotificationDelivery.created_at.desc(),
            NotificationDelivery.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return NotificationDeliveryListResponse(
        items=[NotificationDeliveryResponse.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/notifications/history",
    response_model=NotificationHistoryListResponse,
)
def get_user_notification_history(
    channel: Literal["in_app", "email"] | None = Query(default=None),
    status: Literal["PENDING", "PROCESSING", "SENT", "FAILED", "DEAD_LETTER", "SUPPRESSED"] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationHistoryListResponse:
    """Retrieve user-scoped notification history with delivery status and timestamps."""
    query = db.query(NotificationDelivery).filter(
        NotificationDelivery.user_id == current.id
    )

    if channel is not None:
        query = query.filter(NotificationDelivery.channel == channel)
    if status is not None:
        query = query.filter(NotificationDelivery.status == status)

    total = query.count()
    records = (
        query.order_by(
            NotificationDelivery.created_at.desc(),
            NotificationDelivery.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        NotificationHistoryItemResponse(
            id=rec.id,
            user_id=rec.user_id,
            channel=rec.channel,
            notification_event=rec.notification_event,
            status=rec.status,
            alert_id=rec.alert_id,
            digest_id=rec.digest_id,
            delivered_at=rec.delivered_at,
            created_at=rec.created_at,
            failure_reason=rec.failure_reason,
        )
        for rec in records
    ]

    return NotificationHistoryListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/notifications/digest/evaluate",
    response_model=DigestEvaluationResponse,
)
def evaluate_user_daily_digest(
    background_tasks: BackgroundTasks,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DigestEvaluationResponse:
    """Evaluate and generate daily financial digest for the current user."""
    pref = get_or_create_user_preferences(db, current.id)
    local_date, _, _ = get_user_local_date_and_time(pref.timezone)

    digest, reason = generate_daily_digest_for_user(
        db,
        current.id,
        force=True,  # User-initiated explicit manual evaluation
    )

    if digest is not None:
        background_tasks.add_task(dispatch_pending_user_deliveries, current.id)

    status_mapping = {
        "generated": "generated",
        "already_generated": "already_generated",
        "skipped_no_alerts": "skipped_no_alerts",
        "skipped_disabled": "skipped_disabled",
        "skipped_no_consent": "skipped_disabled",
    }
    status_val = status_mapping.get(reason, "skipped_disabled")

    messages = {
        "generated": f"Daily digest generated with {digest.item_count if digest else 0} alerts.",
        "already_generated": "Daily digest has already been generated for today.",
        "skipped_no_alerts": "No eligible financial alerts found for today's digest.",
        "skipped_disabled": "Email digest is disabled or email consent has not been granted.",
    }

    return DigestEvaluationResponse(
        status=status_val,
        digest_id=digest.id if digest else None,
        item_count=digest.item_count if digest else 0,
        local_date=local_date,
        message=messages.get(status_val, "Digest evaluation completed."),
    )


@router.get(
    "/notifications/digests",
    response_model=list[NotificationDigestResponse],
)
def get_user_digests(
    limit: int = Query(default=10, ge=1, le=50),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NotificationDigestResponse]:
    """Retrieve historical daily digests for the current user."""
    digests = (
        db.query(NotificationDigest)
        .filter(NotificationDigest.user_id == current.id)
        .order_by(NotificationDigest.local_date.desc(), NotificationDigest.id.desc())
        .limit(limit)
        .all()
    )
    return [NotificationDigestResponse.model_validate(d) for d in digests]
