"""Deterministic proactive financial alerts engine (AI-15L).

Evaluates user-scoped financial conditions from authoritative services:
- Runway and cash position (AI-15D)
- Obligation reconciliation and cashflow items (AI-15B, AI-15C)
- Account position and reconciliation (AI-15A, AI-15K)
- Coaching recommendations and feedback (AI-15F, AI-15G)

Guarantees:
- Deterministic deduplication by stable alert_key
- Insufficient data is never treated as zero or alerted upon
- Idempotent repeated evaluations
- Meaningful change detection and escalation
- Strict owner isolation
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from fastapi import HTTPException
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.financial_alert import FinancialAlert
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.user import User
from app.schemas.financial_alerts import (
    AlertEvaluationSummary,
    FinancialAlertResponse,
)
from app.services.finance.account_position import get_account_overview
from app.services.finance.coaching_feedback import visible_coaching
from app.services.finance.obligations import obligation_amounts_for_items
from app.services.finance.runway import financial_runway
from app.services.intelligence.periods import today_dhaka
from app.services.notifications.dispatcher import enqueue_notifications_for_alert
import logging

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")
LARGE_CASH_FRACTION = Decimal("0.50")

SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


@dataclass(frozen=True)
class AlertCandidate:
    """An evaluated financial condition candidate for alert generation."""

    alert_key: str
    alert_type: str
    severity: str
    title: str
    title_key: str
    message: str
    message_key: str
    evidence: dict[str, Any]
    recommended_action: str
    action_url: str | None = None


def lock_user_for_evaluation(db: Session, user_id: int) -> None:
    """Acquire a row-level lock on the user record to serialize evaluation transactions."""
    bind = db.get_bind()
    if bind and bind.dialect.name == "postgresql":
        db.query(User).filter(User.id == user_id).with_for_update().one()


def to_alert_response(alert: FinancialAlert) -> FinancialAlertResponse:
    """Map FinancialAlert model to FinancialAlertResponse schema with computed is_read."""
    return FinancialAlertResponse(
        id=alert.id,
        user_id=alert.user_id,
        alert_key=alert.alert_key,
        alert_type=alert.alert_type,
        severity=alert.severity,  # type: ignore[arg-type]
        title=alert.title,
        title_key=alert.title_key,
        message=alert.message,
        message_key=alert.message_key,
        evidence=alert.evidence or {},
        recommended_action=alert.recommended_action,
        action_url=alert.action_url,
        status=alert.status,  # type: ignore[arg-type]
        is_read=alert.read_at is not None,
        first_detected_at=alert.first_detected_at,
        last_detected_at=alert.last_detected_at,
        resolved_at=alert.resolved_at,
        read_at=alert.read_at,
        dismissed_at=alert.dismissed_at,
        actioned_at=alert.actioned_at,
        occurrence_count=alert.occurrence_count,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


def evaluate_candidates(
    db: Session,
    user_id: int,
    *,
    as_of: date | None = None,
    observed_at: datetime | None = None,
    safety_threshold: Decimal = ZERO,
) -> tuple[list[AlertCandidate], dict[str, Any]]:
    """Deterministically detect all active condition candidates for the user.

    Returns the candidates and context metadata for resolution decisions.
    """
    as_of = as_of or today_dhaka()
    observed_at_dt = observed_at or datetime.now(timezone.utc)
    candidates: list[AlertCandidate] = []

    # 1. Cash Position Risk (AI-15D Runway & AI-15F Coaching pattern)
    runway = financial_runway(
        db,
        user_id,
        as_of=as_of,
        safety_threshold=safety_threshold,
    )
    if runway.starting_balance is not None and runway.known_obligations_end_balance is not None:
        if runway.known_obligations_end_balance <= safety_threshold:
            known = financial_runway(
                db,
                user_id,
                as_of=as_of,
                mode="known_obligations",
                safety_threshold=safety_threshold,
            )
            if runway.runway_status == "insufficient_data" or known.runway_status == "cash_shortfall":
                runway = known
        elif runway.runway_status == "insufficient_data":
            known = financial_runway(
                db,
                user_id,
                as_of=as_of,
                mode="known_obligations",
                safety_threshold=safety_threshold,
            )
            if known.runway_status == "positive":
                runway = known

    # Insufficient data must NEVER generate an alert
    if runway.runway_status != "insufficient_data":
        if runway.runway_status == "cash_shortfall":
            candidates.append(
                AlertCandidate(
                    alert_key="cash_position:runway_risk",
                    alert_type="cash_shortfall",
                    severity="critical",
                    title="Projected Cash Shortfall",
                    title_key="alert_title_cash_shortfall",
                    message=(
                        f"Projected cash position falls below zero BDT within the 30-day "
                        f"horizon (minimum projected balance: {runway.minimum_projected_balance} BDT)."
                    ),
                    message_key="alert_msg_cash_shortfall",
                    recommended_action="Review upcoming obligations and postpone non-essential spending.",
                    action_url="/cashflow",
                    evidence={
                        "starting_balance": str(runway.starting_balance),
                        "minimum_projected_balance": str(runway.minimum_projected_balance),
                        "scheduled_expense_reserve": str(runway.scheduled_expense_reserve),
                        "runway_status": runway.runway_status,
                        "as_of_date": as_of.isoformat(),
                        "observed_at": observed_at_dt.isoformat(),
                    },
                )
            )
        elif runway.runway_status == "at_risk":
            candidates.append(
                AlertCandidate(
                    alert_key="cash_position:runway_risk",
                    alert_type="cash_at_risk",
                    severity="high",
                    title="Cash Position at Risk",
                    title_key="alert_title_cash_at_risk",
                    message=(
                        f"Projected cash position drops to or below your safety threshold "
                        f"({runway.safety_threshold} BDT) within the 30-day horizon."
                    ),
                    message_key="alert_msg_cash_at_risk",
                    recommended_action="Review planned cashflow to maintain your safety reserve.",
                    action_url="/cashflow",
                    evidence={
                        "starting_balance": str(runway.starting_balance),
                        "minimum_projected_balance": str(runway.minimum_projected_balance),
                        "safety_threshold": str(runway.safety_threshold),
                        "runway_status": runway.runway_status,
                        "as_of_date": as_of.isoformat(),
                        "observed_at": observed_at_dt.isoformat(),
                    },
                )
            )

    # 2. Upcoming & Overdue Obligations (AI-15B, AI-15C)
    items = (
        db.query(ScheduledCashflowItem)
        .filter(
            ScheduledCashflowItem.user_id == user_id,
            ScheduledCashflowItem.kind == "expense",
            ScheduledCashflowItem.status == "scheduled",
        )
        .order_by(ScheduledCashflowItem.due_date.asc())
        .all()
    )

    as_of_dt = datetime.combine(as_of, datetime.min.time(), tzinfo=timezone.utc)
    amounts_by_id = obligation_amounts_for_items(db, user_id, items, as_of=as_of_dt)

    for item in items:
        amounts = amounts_by_id[item.id]
        if amounts.remaining_amount <= ZERO:
            continue

        days_until_due = (item.due_date - as_of).days

        if days_until_due < 0:
            # Overdue obligation
            overdue_days = abs(days_until_due)
            severity = "critical" if overdue_days > 7 else "high"
            candidates.append(
                AlertCandidate(
                    alert_key=f"obligation:{item.id}:due",
                    alert_type="obligation_overdue",
                    severity=severity,
                    title=f"Overdue Obligation: {item.title}",
                    title_key="alert_title_obligation_overdue",
                    message=(
                        f"Scheduled expense '{item.title}' was due on {item.due_date.isoformat()} "
                        f"and has BDT {amounts.remaining_amount} remaining unpaid."
                    ),
                    message_key="alert_msg_obligation_overdue",
                    recommended_action="Confirm payment or allocate an existing transaction.",
                    action_url="/cashflow",
                    evidence={
                        "item_id": item.id,
                        "title": item.title,
                        "due_date": item.due_date.isoformat(),
                        "remaining_amount": str(amounts.remaining_amount),
                        "allocated_amount": str(amounts.allocated_amount),
                        "original_amount": str(amounts.original_amount),
                        "days_overdue": overdue_days,
                        "as_of_date": as_of.isoformat(),
                        "observed_at": observed_at_dt.isoformat(),
                    },
                )
            )
        elif 0 <= days_until_due <= 3 or (
            runway.starting_balance is not None
            and runway.starting_balance > ZERO
            and amounts.remaining_amount >= runway.starting_balance * LARGE_CASH_FRACTION
            and days_until_due <= 7
        ):
            # Due soon or large obligation approaching
            severity = "high" if days_until_due <= 1 else "medium"
            candidates.append(
                AlertCandidate(
                    alert_key=f"obligation:{item.id}:due",
                    alert_type="obligation_due_soon",
                    severity=severity,
                    title=f"Upcoming Obligation: {item.title}",
                    title_key="alert_title_obligation_due_soon",
                    message=(
                        f"Scheduled expense '{item.title}' is due on {item.due_date.isoformat()} "
                        f"for BDT {amounts.remaining_amount}."
                    ),
                    message_key="alert_msg_obligation_due_soon",
                    recommended_action="Reserve funds and confirm settlement when paid.",
                    action_url="/cashflow",
                    evidence={
                        "item_id": item.id,
                        "title": item.title,
                        "due_date": item.due_date.isoformat(),
                        "remaining_amount": str(amounts.remaining_amount),
                        "allocated_amount": str(amounts.allocated_amount),
                        "original_amount": str(amounts.original_amount),
                        "days_until_due": days_until_due,
                        "as_of_date": as_of.isoformat(),
                        "observed_at": observed_at_dt.isoformat(),
                    },
                )
            )

    # 3. Account Position Reliability (AI-15A, AI-15K)
    account_overview = get_account_overview(db, user_id)
    for acc in account_overview.items:
        if acc.position_status == "unreconciled":
            diff = acc.reconciliation.difference
            candidates.append(
                AlertCandidate(
                    alert_key=f"account:{acc.id}:reconciliation_mismatch",
                    alert_type="account_unreconciled",
                    severity="medium",
                    title=f"Account Balance Mismatch: {acc.name}",
                    title_key="alert_title_account_mismatch",
                    message=(
                        f"Account '{acc.name}' reported balance differs from calculated transactions "
                        f"by BDT {diff}."
                    ),
                    message_key="alert_msg_account_mismatch",
                    recommended_action="Review transactions or update the reported balance.",
                    action_url="/accounts",
                    evidence={
                        "account_id": acc.id,
                        "account_name": acc.name,
                        "reported_balance": str(acc.current_balance) if acc.current_balance is not None else None,
                        "derived_balance": str(acc.reconciliation.derived_balance) if acc.reconciliation.derived_balance is not None else None,
                        "difference": str(diff) if diff is not None else None,
                        "as_of_date": as_of.isoformat(),
                        "observed_at": observed_at_dt.isoformat(),
                    },
                )
            )

    # 4. Coaching Recommendations (AI-15F, AI-15G)
    coaching = visible_coaching(db, user_id, as_of=as_of)
    for rec in coaching.recommendations:
        if rec.type == "goal_risk":
            candidates.append(
                AlertCandidate(
                    alert_key=f"coaching:{rec.id}",
                    alert_type="savings_goal_at_risk",
                    severity=rec.priority,
                    title=rec.title,
                    title_key="alert_title_goal_risk",
                    message=rec.description,
                    message_key="alert_msg_goal_risk",
                    recommended_action=rec.recommended_action,
                    action_url="/plans",
                    evidence={
                        "goal_id": rec.evidence.get("goal_id") if isinstance(rec.evidence, dict) else None,
                        "goal_name": rec.evidence.get("goal_name") if isinstance(rec.evidence, dict) else None,
                        "remaining_amount": str(rec.evidence.get("remaining_amount")) if isinstance(rec.evidence, dict) else None,
                        "as_of_date": as_of.isoformat(),
                        "observed_at": observed_at_dt.isoformat(),
                    },
                )
            )
        elif rec.type == "spending_spike":
            candidates.append(
                AlertCandidate(
                    alert_key=f"coaching:{rec.id}",
                    alert_type="spending_spike",
                    severity="medium",
                    title=rec.title,
                    title_key="alert_title_spending_spike",
                    message=rec.description,
                    message_key="alert_msg_spending_spike",
                    recommended_action=rec.recommended_action,
                    action_url="/transactions",
                    evidence={
                        "category": rec.evidence.get("category") if isinstance(rec.evidence, dict) else None,
                        "percentage_change": str(rec.evidence.get("percentage_change")) if isinstance(rec.evidence, dict) else None,
                        "as_of_date": as_of.isoformat(),
                        "observed_at": observed_at_dt.isoformat(),
                    },
                )
            )

    context = {
        "runway_status": runway.runway_status,
        "active_account_ids": {acc.id for acc in account_overview.items},
        "trusted_account_ids": {acc.id for acc in account_overview.items if acc.position_status == "trusted"},
        "coaching_rec_ids": {rec.id for rec in coaching.recommendations},
    }

    return candidates, context


def evaluate_alerts(
    db: Session,
    user_id: int,
    *,
    as_of: date | None = None,
    safety_threshold: Decimal = ZERO,
) -> AlertEvaluationSummary:
    """Evaluate financial conditions and synchronize persistent user alerts idempotently."""
    lock_user_for_evaluation(db, user_id)
    now = datetime.now(timezone.utc)
    as_of = as_of or today_dhaka()

    candidates, context = evaluate_candidates(
        db,
        user_id,
        as_of=as_of,
        observed_at=now,
        safety_threshold=safety_threshold,
    )

    existing_alerts: dict[str, FinancialAlert] = {
        alert.alert_key: alert
        for alert in db.query(FinancialAlert).filter(FinancialAlert.user_id == user_id).all()
    }

    created = 0
    updated = 0
    resolved = 0
    unchanged = 0
    events_to_dispatch: list[tuple[FinancialAlert, str]] = []

    candidate_keys = {c.alert_key for c in candidates}

    for candidate in candidates:
        if candidate.alert_key not in existing_alerts:
            # 1. New alert condition detected
            new_alert = FinancialAlert(
                user_id=user_id,
                alert_key=candidate.alert_key,
                alert_type=candidate.alert_type,
                severity=candidate.severity,
                title=candidate.title,
                title_key=candidate.title_key,
                message=candidate.message,
                message_key=candidate.message_key,
                evidence=candidate.evidence,
                recommended_action=candidate.recommended_action,
                action_url=candidate.action_url,
                status="active",
                first_detected_at=now,
                last_detected_at=now,
                resolved_at=None,
                read_at=None,
                dismissed_at=None,
                actioned_at=None,
                occurrence_count=1,
                created_at=now,
                updated_at=now,
            )
            db.add(new_alert)
            created += 1
            events_to_dispatch.append((new_alert, 'ALERT_CREATED'))
        else:
            existing = existing_alerts[candidate.alert_key]

            if existing.status == "resolved":
                # 2. Reappearance after prior resolution: new user-attention event
                existing.status = "active"
                existing.resolved_at = None
                existing.read_at = None
                existing.dismissed_at = None
                existing.actioned_at = None
                existing.severity = candidate.severity
                existing.alert_type = candidate.alert_type
                existing.title = candidate.title
                existing.title_key = candidate.title_key
                existing.message = candidate.message
                existing.message_key = candidate.message_key
                existing.evidence = candidate.evidence
                existing.recommended_action = candidate.recommended_action
                existing.action_url = candidate.action_url
                existing.last_detected_at = now
                existing.occurrence_count += 1
                existing.updated_at = now
                updated += 1
                events_to_dispatch.append((existing, 'ALERT_RECURRED'))

            elif existing.status == "dismissed":
                # 3. Escalation check on dismissed condition
                # Critical warnings must never be hidden by prior dismissal of lesser risk
                is_escalation_to_critical = (
                    candidate.severity == "critical" and existing.severity != "critical"
                )
                if is_escalation_to_critical:
                    existing.status = "active"
                    existing.resolved_at = None
                    existing.read_at = None
                    existing.dismissed_at = None
                    existing.actioned_at = None
                    existing.severity = candidate.severity
                    existing.alert_type = candidate.alert_type
                    existing.title = candidate.title
                    existing.title_key = candidate.title_key
                    existing.message = candidate.message
                    existing.message_key = candidate.message_key
                    existing.evidence = candidate.evidence
                    existing.recommended_action = candidate.recommended_action
                    existing.action_url = candidate.action_url
                    existing.last_detected_at = now
                    existing.occurrence_count += 1
                    existing.updated_at = now
                    updated += 1
                    events_to_dispatch.append((existing, 'ALERT_ESCALATED'))
                else:
                    # Preserve dismissal and its dismissal timestamp; update detection timestamp and evidence
                    # Note: occurrence_count is NOT incremented
                    existing.last_detected_at = now
                    existing.evidence = candidate.evidence
                    existing.updated_at = now
                    unchanged += 1

            else:
                # 4. Ongoing active condition: check for meaningful changes
                severity_changed = existing.severity != candidate.severity
                type_changed = existing.alert_type != candidate.alert_type
                title_changed = existing.title != candidate.title
                message_changed = existing.message != candidate.message

                if severity_changed or type_changed or title_changed or message_changed:
                    # Meaningful change detected
                    escalated_to_critical = (
                        candidate.severity == "critical" and existing.severity != "critical"
                    )
                    old_sev_rank = SEVERITY_ORDER.get(existing.severity, 99)
                    new_sev_rank = SEVERITY_ORDER.get(candidate.severity, 99)
                    is_escalated = escalated_to_critical or (new_sev_rank < old_sev_rank)
                    existing.severity = candidate.severity
                    existing.alert_type = candidate.alert_type
                    existing.title = candidate.title
                    existing.title_key = candidate.title_key
                    existing.message = candidate.message
                    existing.message_key = candidate.message_key
                    existing.evidence = candidate.evidence
                    existing.recommended_action = candidate.recommended_action
                    existing.action_url = candidate.action_url
                    existing.last_detected_at = now
                    existing.occurrence_count += 1
                    existing.updated_at = now
                    if escalated_to_critical:
                        existing.read_at = None  # Escalation requires re-reading
                        existing.actioned_at = None  # Material escalation invalidates prior non-critical action
                    updated += 1
                    if is_escalated:
                        events_to_dispatch.append((existing, 'ALERT_ESCALATED'))
                else:
                    # Idempotent unchanged evaluation: read_at and actioned_at preserved
                    existing.last_detected_at = now
                    existing.evidence = candidate.evidence
                    unchanged += 1

    # Check for resolution of existing active alerts
    for alert_key, existing in existing_alerts.items():
        if existing.status == "active" and alert_key not in candidate_keys:
            # Check if resolution can be reliably established
            should_resolve = False

            if alert_key == "cash_position:runway_risk":
                # If runway is now verified positive, resolve cash risk
                if context["runway_status"] == "positive":
                    should_resolve = True

            elif alert_key.startswith("obligation:"):
                # Obligation is no longer an active candidate (paid, cancelled, or remaining is 0)
                # Check underlying scheduled cashflow item
                parts = alert_key.split(":")
                if len(parts) >= 2 and parts[1].isdigit():
                    item_id = int(parts[1])
                    item = db.query(ScheduledCashflowItem).filter_by(id=item_id, user_id=user_id).first()
                    if item is None or item.status in ("paid", "cancelled"):
                        should_resolve = True
                    else:
                        # Item still exists; check remaining amounts
                        amounts_map = obligation_amounts_for_items(
                            db, user_id, [item], as_of=datetime.combine(as_of, datetime.min.time(), tzinfo=timezone.utc)
                        )
                        if amounts_map[item.id].remaining_amount <= ZERO:
                            should_resolve = True
                        elif (item.due_date - as_of).days > 7:
                            # Due date was moved out beyond alert horizon
                            should_resolve = True

            elif alert_key.startswith("account:"):
                # Account reconciliation mismatch
                parts = alert_key.split(":")
                if len(parts) >= 2 and parts[1].isdigit():
                    acc_id = int(parts[1])
                    if acc_id not in context["active_account_ids"] or acc_id in context["trusted_account_ids"]:
                        should_resolve = True

            elif alert_key.startswith("coaching:"):
                # Coaching recommendation no longer active
                parts = alert_key.split(":", 1)
                rec_id = parts[1] if len(parts) == 2 else ""
                if rec_id not in context["coaching_rec_ids"]:
                    should_resolve = True

            if should_resolve:
                existing.status = "resolved"
                existing.resolved_at = now
                existing.updated_at = now
                resolved += 1

    db.flush()
    for alert_obj, event_type in events_to_dispatch:
        try:
            enqueue_notifications_for_alert(db, alert_obj, event_type)
        except Exception as err:
            logger.error(
                "Failed to enqueue notification delivery for alert %s: %s",
                getattr(alert_obj, "id", None),
                err,
            )

    db.commit()

    return AlertEvaluationSummary(
        created=created,
        updated=updated,
        resolved=resolved,
        unchanged=unchanged,
        evaluated_at=now,
    )


def list_alerts(
    db: Session,
    user_id: int,
    *,
    status: str | None = None,
    unread_only: bool = False,
    severity: str | None = None,
    alert_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[FinancialAlertResponse], int]:
    """Retrieve owner-scoped alerts with deterministic priority ordering and bounded pagination."""
    bounded_limit = min(max(1, limit), 100)
    bounded_offset = max(0, offset)

    query = db.query(FinancialAlert).filter(FinancialAlert.user_id == user_id)

    if status:
        query = query.filter(FinancialAlert.status == status)
    if unread_only:
        query = query.filter(FinancialAlert.read_at.is_(None), FinancialAlert.status == "active")
    if severity:
        query = query.filter(FinancialAlert.severity == severity)
    if alert_type:
        query = query.filter(FinancialAlert.alert_type == alert_type)

    total = query.count()

    # Deterministic sorting:
    # 1. Severity: critical (0), high (1), medium (2), low (3), info (4)
    # 2. Status: active (0), dismissed (1), resolved (2)
    # 3. Detection time descending, then ID descending
    severity_case = case(
        (FinancialAlert.severity == "critical", 0),
        (FinancialAlert.severity == "high", 1),
        (FinancialAlert.severity == "medium", 2),
        (FinancialAlert.severity == "low", 3),
        else_=4,
    )
    status_case = case(
        (FinancialAlert.status == "active", 0),
        (FinancialAlert.status == "dismissed", 1),
        else_=2,
    )

    items = (
        query.order_by(
            severity_case.asc(),
            status_case.asc(),
            FinancialAlert.last_detected_at.desc(),
            FinancialAlert.id.desc(),
        )
        .offset(bounded_offset)
        .limit(bounded_limit)
        .all()
    )

    return [to_alert_response(alert) for alert in items], total


def get_unread_count(db: Session, user_id: int) -> int:
    """Compute total count of unread active alerts across the entire user scope."""
    return (
        db.query(FinancialAlert)
        .filter(
            FinancialAlert.user_id == user_id,
            FinancialAlert.status == "active",
            FinancialAlert.read_at.is_(None),
        )
        .count()
    )


def mark_alert_read(db: Session, user_id: int, alert_id: int) -> FinancialAlertResponse:
    """Mark an alert as read by setting read_at. Safe to call repeatedly."""
    alert = (
        db.query(FinancialAlert)
        .filter(
            FinancialAlert.id == alert_id,
            FinancialAlert.user_id == user_id,
        )
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.read_at is None:
        now = datetime.now(timezone.utc)
        alert.read_at = now
        alert.updated_at = now
        db.commit()
        db.refresh(alert)

    return to_alert_response(alert)


def dismiss_alert(db: Session, user_id: int, alert_id: int) -> FinancialAlertResponse:
    """Dismiss an active alert. Preserves history and dismissal timestamp."""
    alert = (
        db.query(FinancialAlert)
        .filter(
            FinancialAlert.id == alert_id,
            FinancialAlert.user_id == user_id,
        )
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.status != "dismissed":
        now = datetime.now(timezone.utc)
        alert.status = "dismissed"
        alert.dismissed_at = now
        alert.updated_at = now
        db.commit()
        db.refresh(alert)

    return to_alert_response(alert)


def mark_alert_actioned(db: Session, user_id: int, alert_id: int) -> FinancialAlertResponse:
    """Record user assertion that recommended action was taken without verifying financial fact."""
    alert = (
        db.query(FinancialAlert)
        .filter(
            FinancialAlert.id == alert_id,
            FinancialAlert.user_id == user_id,
        )
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    now = datetime.now(timezone.utc)
    alert.actioned_at = now
    alert.updated_at = now
    db.commit()
    db.refresh(alert)

    return to_alert_response(alert)


def restore_alert(db: Session, user_id: int, alert_id: int) -> FinancialAlertResponse:
    """Restore a dismissed alert back to active status."""
    alert = (
        db.query(FinancialAlert)
        .filter(
            FinancialAlert.id == alert_id,
            FinancialAlert.user_id == user_id,
        )
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.status == "dismissed":
        now = datetime.now(timezone.utc)
        alert.status = "active"
        alert.dismissed_at = None
        alert.updated_at = now
        db.commit()
        db.refresh(alert)

    return to_alert_response(alert)
