"""Authenticated API endpoints for proactive financial alerts."""
from typing import Literal
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from app.services.notifications.dispatcher import dispatch_pending_user_deliveries
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.financial_alerts import (
    AlertEvaluationSummary,
    AlertListResponse,
    AlertUnreadCountResponse,
    FinancialAlertResponse,
)
from app.services.finance.financial_alerts import (
    dismiss_alert,
    evaluate_alerts,
    get_unread_count,
    list_alerts,
    mark_alert_actioned,
    mark_alert_read,
    restore_alert,
)

router = APIRouter(
    prefix="/finance/alerts",
    tags=["financial alerts"],
)


@router.post("/evaluate", response_model=AlertEvaluationSummary)
def evaluate_user_alerts(
    background_tasks: BackgroundTasks,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertEvaluationSummary:
    """Evaluate financial conditions for the authenticated user and sync alerts."""
    summary = evaluate_alerts(db, current.id)
    background_tasks.add_task(dispatch_pending_user_deliveries, current.id)
    return summary


@router.get("", response_model=AlertListResponse)
def get_alerts(
    status: Literal["active", "resolved", "dismissed"] | None = Query(default=None),
    unread_only: bool = Query(default=False),
    severity: Literal["critical", "high", "medium", "low", "info"] | None = Query(default=None),
    alert_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertListResponse:
    """Retrieve owner-scoped financial alerts with deterministic ordering and filtering."""
    items, total = list_alerts(
        db,
        current.id,
        status=status,
        unread_only=unread_only,
        severity=severity,
        alert_type=alert_type,
        limit=limit,
        offset=offset,
    )
    return AlertListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=AlertUnreadCountResponse)
def get_user_unread_count(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertUnreadCountResponse:
    """Get the total count of unread active alerts for the current user."""
    count = get_unread_count(db, current.id)
    return AlertUnreadCountResponse(unread_count=count)


@router.patch("/{alert_id}/read", response_model=FinancialAlertResponse)
def read_alert(
    alert_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialAlertResponse:
    """Mark an alert as read by setting read_at timestamp."""
    return mark_alert_read(db, current.id, alert_id)


@router.patch("/{alert_id}/dismiss", response_model=FinancialAlertResponse)
def dismiss_user_alert(
    alert_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialAlertResponse:
    """Dismiss an active alert and record the dismissal timestamp."""
    return dismiss_alert(db, current.id, alert_id)


@router.patch("/{alert_id}/actioned", response_model=FinancialAlertResponse)
def action_user_alert(
    alert_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialAlertResponse:
    """Record user assertion that suggested action was taken."""
    return mark_alert_actioned(db, current.id, alert_id)


@router.post("/{alert_id}/restore", response_model=FinancialAlertResponse)
def restore_user_alert(
    alert_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialAlertResponse:
    """Restore a dismissed alert back to active status."""
    return restore_alert(db, current.id, alert_id)
