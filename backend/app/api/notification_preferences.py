"""Authenticated API endpoints for user notification preferences and delivery outbox."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.notification_delivery import NotificationDelivery
from app.models.notification_preference import NotificationPreference
from app.models.user import User
from app.schemas.notification_delivery import (
    NotificationDeliveryListResponse,
    NotificationDeliveryResponse,
)
from app.schemas.notification_preferences import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)
from app.services.notifications.dispatcher import (
    get_or_create_user_preferences,
)

router = APIRouter(
    prefix="/finance",
    tags=["notification preferences"],
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
