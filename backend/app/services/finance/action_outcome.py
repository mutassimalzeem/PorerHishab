"""Derived outcome observations over existing authoritative services (AI-15I).

This module is deliberately read-only. It never recalculates balances, spending,
cashflow, runway, goal affordability or obligation settlement: it asks the
existing services for the same values they already expose and compares two
deterministic observation windows.

The user's ``acted_on`` feedback says only that the user reported acting. It is
never treated as verified behaviour, and an observed change is never described
as caused by the recommendation.
"""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.obligation_allocation import ObligationAllocation
from app.models.coaching_feedback import CoachingFeedback
from app.models.savings_goal import SavingsGoal
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.transactions import Transaction
from app.schemas.action_outcome import (
    ActionOutcome,
    ActionOutcomeReport,
    ActionOutcomeSummary,
    OutcomeEvidence,
    OutcomeObligation,
    OutcomeWindow,
)
from app.schemas.coaching import CoachingType
from app.services.finance.coaching import financial_coaching
from app.services.finance.obligations import obligation_amounts_for_items
from app.services.finance.runway import financial_runway
from app.services.intelligence.facts import totals
from app.services.intelligence.periods import money, today_dhaka
from app.services.intelligence.signals import stable_category_token

ZERO = Decimal("0.00")
PERCENT = Decimal("100")
PERCENT_SCALE = Decimal("0.01")
#: The longest follow-up window an outcome will compare.
OBSERVATION_DAYS = 30
#: Below this many elapsed days the outcome is pending, never a result.
MIN_FOLLOW_UP_DAYS = 7
DHAKA = ZoneInfo("Asia/Dhaka")

COACHING_TYPES = {
    "cash_risk",
    "upcoming_obligations",
    "spending_spike",
    "repeated_spending",
    "savings_opportunity",
    "goal_risk",
}

BASE_LIMITATIONS = [
    "The user reported acting on this recommendation; the system cannot verify the action itself.",
    "Observed change does not establish that the recommendation caused the change.",
    "Only recorded BDT evidence is compared; foreign-currency accounts are excluded without conversion.",
]
REPORT_LIMITATIONS = [
    "Only acted-on recommendations are normally tracked; dismissed, not-relevant, snoozed and unrated recommendations are excluded.",
    "Rolling follow-ups are capped at 30 days; spending evidence months require an equal full follow-up of up to 31 days. The minimum observation is 7 days.",
    "A missing outcome is not a failed action. Insufficient data means the system cannot make a comparable observation.",
    "Outcomes are derived from current financial state each time; they are not a stored historical audit of the action.",
    "This layer is observation-only and makes no causal claim.",
]


def _dhaka_date(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(DHAKA).date()


def _windows(action_date: date, as_of: date) -> tuple[OutcomeWindow, OutcomeWindow, int]:
    """Equal-length windows immediately around the action reporting date.

    The baseline ends on the action date. The follow-up starts the next day and
    lasts at most ``OBSERVATION_DAYS``. Both windows have the same number of
    days so a partial follow-up is never compared with a full month.
    """
    elapsed = (as_of - action_date).days
    observed = max(0, min(elapsed, OBSERVATION_DAYS))
    follow_up_start = action_date + timedelta(days=1)
    if observed == 0:
        follow_up = OutcomeWindow(start=follow_up_start, end=follow_up_start,
                                  days=0, is_complete=False)
        baseline = OutcomeWindow(start=action_date, end=action_date,
                                 days=0, is_complete=True)
    else:
        follow_up_end = action_date + timedelta(days=observed)
        follow_up = OutcomeWindow(start=follow_up_start, end=follow_up_end,
                                  days=observed, is_complete=follow_up_end <= as_of)
        baseline = OutcomeWindow(
            start=action_date - timedelta(days=observed - 1),
            end=action_date, days=observed, is_complete=True)
    return baseline, follow_up, elapsed


def _spending_windows(recommendation_id, action_date, as_of):
    """Recover the original complete evidence month from the stable coaching ID.

    Coaching spending IDs encode the observed month, even after advice expires.
    Wait for an equally long follow-up rather than comparing a partial month.
    Legacy identities without an eligible month use documented rolling windows.
    """
    try:
        year, month = map(int, recommendation_id.rsplit(":", 1)[1].split("-"))
        start = date(year, month, 1)
        days = monthrange(year, month)[1]
        end = date(year, month, days)
    except (ValueError, IndexError):
        return _windows(action_date, as_of)
    if end > action_date:
        return _windows(action_date, as_of)
    follow_start = action_date + timedelta(days=1)
    follow_end = action_date + timedelta(days=days)
    return (
        OutcomeWindow(start=start, end=end, days=days, is_complete=True),
        OutcomeWindow(start=follow_start, end=follow_end, days=days,
                      is_complete=as_of >= follow_end),
        (as_of - action_date).days,
    )


def _cash_windows(action_date: date, as_of: date) -> tuple[OutcomeWindow, OutcomeWindow]:
    """Forward-looking cash projections anchored at the action and observation dates."""
    baseline_start, baseline_end = action_date, action_date + timedelta(days=OBSERVATION_DAYS)
    follow_start, follow_end = as_of, as_of + timedelta(days=OBSERVATION_DAYS)
    return (
        OutcomeWindow(start=baseline_start, end=baseline_end,
                      days=(baseline_end - baseline_start).days + 1,
                      is_complete=baseline_end <= as_of),
        OutcomeWindow(start=follow_start, end=follow_end,
                      days=(follow_end - follow_start).days + 1,
                      is_complete=False),
    )


def _percentage_change(before: Decimal, after: Decimal) -> Decimal | None:
    """Signed percentage change using ``abs(before)``; zero baselines are undefined."""
    if before == ZERO:
        return None
    return ((after - before) / abs(before) * PERCENT).quantize(
        PERCENT_SCALE, rounding=ROUND_HALF_EVEN)


def _classify(before: Decimal, after: Decimal,
              direction: Literal["lower_is_better", "higher_is_better", "neutral"]) -> str:
    change = money(after - before)
    if change == ZERO:
        return "unchanged"
    if direction == "lower_is_better":
        return "improved" if change < ZERO else "worsened"
    if direction == "higher_is_better":
        return "improved" if change > ZERO else "worsened"
    return "unchanged"


def _interpretation(status: str, direction: str) -> str:
    if status == "pending":
        return "pending"
    if status == "insufficient_data":
        return "insufficient_data"
    if status == "unchanged":
        return "unchanged"
    if direction == "lower_is_better":
        return "decreased" if status == "improved" else "increased"
    return "increased" if status == "improved" else "decreased"


def _user_categories(db: Session, user_id: int) -> list[str]:
    """Distinct category labels from the user's own BDT-scoped records."""
    owned_bdt = db.query(Account.id).filter(
        Account.user_id == user_id, Account.currency == "BDT")
    rows = db.query(Transaction.category).filter(
        Transaction.user_id == user_id,
        Transaction.category.isnot(None),
        or_(Transaction.account_id.is_(None),
            Transaction.account_id.in_(owned_bdt)),
    ).distinct().all()
    return sorted({str(row[0]) for row in rows if row[0]})


def _spending_category(db: Session, user_id: int, recommendation_id: str,
                       current) -> str | None:
    # Current recommendation metadata keeps the exact category and casing.
    if current is not None:
        if current.evidence.category:
            return current.evidence.category
        if current.type in {"spending_spike", "repeated_spending"} and current.subject:
            return current.subject
    parts = recommendation_id.split(":")
    if len(parts) < 2:
        return None
    token = parts[1]
    return next((category for category in _user_categories(db, user_id)
                 if stable_category_token(category) == token), None)


def _goal_for_outcome(db: Session, user_id: int, recommendation_id: str, current):
    goal_id = None
    if current is not None:
        goal_id = current.evidence.goal_id
    if goal_id is None:
        parts = recommendation_id.split(":")
        if len(parts) > 1 and parts[1].isdigit():
            goal_id = int(parts[1])
    if goal_id is None:
        return None
    return db.query(SavingsGoal).filter_by(id=goal_id, user_id=user_id).first()


def _obligation_ids(recommendation_id: str, current) -> list[int] | None:
    if current is not None and current.evidence.obligations:
        return sorted({row.item_id for row in current.evidence.obligations})
    parts = recommendation_id.split(":")
    if len(parts) < 2 or parts[1] == "sha256":
        return None
    try:
        return sorted({int(value) for value in parts[1].split(",") if value})
    except ValueError:
        return None


def _limitations(*extra: str) -> list[str]:
    return list(BASE_LIMITATIONS) + [line for line in extra if line]


def _pending(recommendation_id: str, rec: CoachingType, subject: str | None,
             action_date: date, baseline: OutcomeWindow, follow_up: OutcomeWindow,
             metric: str, direction: str, evidence: OutcomeEvidence,
             extra: list[str], quality: str = "limited"):
    return ActionOutcome(
        recommendation_id=recommendation_id, recommendation_type=rec, subject=subject,
        action_reported_on=action_date, status="pending", metric=metric,
        direction=direction, baseline=baseline, follow_up=follow_up,
        interpretation="pending", evidence_quality=quality, evidence=evidence,
        limitations=_limitations("A minimum 7-day follow-up and any full evidence-month comparison must complete before observation.", *extra))


def _spending_outcome(db: Session, user_id: int, recommendation_id: str,
                      rec: CoachingType, subject: str | None, action_date: date,
                      as_of: date, current) -> ActionOutcome:
    category = _spending_category(db, user_id, recommendation_id, current)
    baseline, follow_up, elapsed = _spending_windows(recommendation_id, action_date, as_of)
    evidence = OutcomeEvidence(category=category)
    if category is None:
        return ActionOutcome(
            recommendation_id=recommendation_id, recommendation_type=rec,
            subject=None, action_reported_on=action_date,
            status="insufficient_data", metric="category_spending",
            direction="lower_is_better", baseline=baseline, follow_up=follow_up,
            interpretation="insufficient_data", evidence_quality="limited",
            evidence=evidence,
            limitations=_limitations(
                "The recommendation's category could not be recovered from the user's own records.",
                "No comparison is made across unrelated categories."))
    if elapsed < MIN_FOLLOW_UP_DAYS or not follow_up.is_complete:
        return _pending(recommendation_id, rec, category, action_date, baseline,
                        follow_up, "category_spending", "lower_is_better", evidence,
                        ["Only %d elapsed day(s) are available." % max(0, elapsed)],
                        quality="recorded")

    base_totals = totals(db, user_id, baseline.start, baseline.end, exclude_transfers=True)
    follow_totals = totals(db, user_id, follow_up.start, follow_up.end, exclude_transfers=True)
    if (base_totals["coverage"]["transaction_count"] == 0
            or follow_totals["coverage"]["transaction_count"] == 0):
        return ActionOutcome(
            recommendation_id=recommendation_id, recommendation_type=rec,
            subject=category, action_reported_on=action_date,
            status="insufficient_data", metric="category_spending",
            direction="lower_is_better", baseline=baseline, follow_up=follow_up,
            interpretation="insufficient_data", evidence_quality="limited",
            evidence=evidence,
            limitations=_limitations(
                "One or both observation windows contain no recorded transactions.",
                "A missing category total is not treated as zero when the whole window is empty."))

    base_category = totals(db, user_id, baseline.start, baseline.end,
                           category=category, exclude_transfers=True)
    follow_category = totals(db, user_id, follow_up.start, follow_up.end,
                             category=category, exclude_transfers=True)
    before = base_category["expenses"] or ZERO
    after = follow_category["expenses"] or ZERO
    evidence.baseline_transaction_count = base_category["coverage"]["transaction_count"]
    evidence.follow_up_transaction_count = follow_category["coverage"]["transaction_count"]
    status = _classify(before, after, "lower_is_better")
    return ActionOutcome(
        recommendation_id=recommendation_id, recommendation_type=rec,
        subject=category, action_reported_on=action_date, status=status,
        metric="category_spending", direction="lower_is_better",
        baseline=baseline, follow_up=follow_up,
        baseline_value=money(before), follow_up_value=money(after),
        absolute_change=money(after - before),
        percentage_change=_percentage_change(before, after),
        interpretation=_interpretation(status, "lower_is_better"),
        evidence_quality="recorded", evidence=evidence,
        limitations=_limitations(
            "Both windows cover the same number of days and exclude explicit transfers.",
            "Category spending is recorded expense magnitude, not proof that every purchase was optional.",
            "A category absent from a non-empty window is treated as zero observed spending."))


def _savings_outcome(db: Session, user_id: int, recommendation_id: str,
                     rec: CoachingType, action_date: date, as_of: date) -> ActionOutcome:
    baseline, follow_up, elapsed = _windows(action_date, as_of)
    evidence = OutcomeEvidence()
    if elapsed < MIN_FOLLOW_UP_DAYS:
        return _pending(recommendation_id, rec, None, action_date, baseline,
                        follow_up, "recorded_net_cashflow", "higher_is_better", evidence,
                        ["Only %d elapsed day(s) are available." % max(0, elapsed)])
    before = totals(db, user_id, baseline.start, baseline.end, exclude_transfers=True)["net"]
    after = totals(db, user_id, follow_up.start, follow_up.end, exclude_transfers=True)["net"]
    if before is None or after is None:
        return ActionOutcome(
            recommendation_id=recommendation_id, recommendation_type=rec,
            action_reported_on=action_date, status="insufficient_data",
            metric="recorded_net_cashflow", direction="higher_is_better",
            baseline=baseline, follow_up=follow_up,
            interpretation="insufficient_data", evidence_quality="limited",
            evidence=evidence,
            limitations=_limitations(
                "One or both observation windows contain no recorded net cashflow.",
                "Savings behaviour cannot be identified reliably from unclassified transfers."))
    status = _classify(before, after, "higher_is_better")
    return ActionOutcome(
        recommendation_id=recommendation_id, recommendation_type=rec,
        action_reported_on=action_date, status=status,
        metric="recorded_net_cashflow", direction="higher_is_better",
        baseline=baseline, follow_up=follow_up,
        baseline_value=money(before), follow_up_value=money(after),
        absolute_change=money(after - before),
        percentage_change=_percentage_change(before, after),
        interpretation=_interpretation(status, "higher_is_better"),
        evidence_quality="recorded", evidence=evidence,
        limitations=_limitations(
            "Recorded net cashflow is income minus expenses; it is not proof that money was transferred to savings.",
            "Explicitly classified transfers are excluded; unclassified transfers may still distort the comparison."))


def _cash_outcome(db: Session, user_id: int, recommendation_id: str,
                  rec: CoachingType, action_date: date, as_of: date) -> ActionOutcome:
    observation_date = min(as_of, action_date + timedelta(days=OBSERVATION_DAYS))
    baseline, follow_up = _cash_windows(action_date, observation_date)
    elapsed = (as_of - action_date).days
    evidence = OutcomeEvidence()
    if elapsed < MIN_FOLLOW_UP_DAYS:
        return _pending(recommendation_id, rec, None, action_date, baseline,
                        follow_up, "minimum_projected_balance", "higher_is_better", evidence,
                        ["Only %d elapsed day(s) are available." % max(0, elapsed)])
    # Runway intentionally reads current scheduled-item state. Do not present a
    # historical comparison when that state changed after the baseline date.
    cutoff = datetime.combine(action_date, time.max, tzinfo=DHAKA).astimezone(timezone.utc)
    changed_items = db.query(ScheduledCashflowItem.id).filter(
        ScheduledCashflowItem.user_id == user_id,
        ScheduledCashflowItem.updated_at > cutoff).first()
    changed_allocations = db.query(ObligationAllocation.id).filter(
        ObligationAllocation.user_id == user_id,
        or_(ObligationAllocation.confirmed_at > cutoff,
            ObligationAllocation.revoked_at > cutoff)).first()
    if changed_items or changed_allocations:
        return ActionOutcome(
            recommendation_id=recommendation_id, recommendation_type=rec,
            action_reported_on=action_date, status="insufficient_data",
            metric="minimum_projected_balance", direction="higher_is_better",
            baseline=baseline, follow_up=follow_up, interpretation="insufficient_data",
            evidence_quality="limited", evidence=evidence,
            limitations=_limitations(
                "The authoritative runway is not available at one or both observation points."))
    base_runway = financial_runway(db, user_id, as_of=action_date,
                                   horizon_days=OBSERVATION_DAYS)
    follow_runway = financial_runway(db, user_id, as_of=observation_date,
                                     horizon_days=OBSERVATION_DAYS)
    evidence.baseline_runway_status = base_runway.runway_status
    evidence.follow_up_runway_status = follow_runway.runway_status
    evidence.baseline_runway_mode = base_runway.mode
    evidence.follow_up_runway_mode = follow_runway.mode
    before = base_runway.minimum_projected_balance
    after = follow_runway.minimum_projected_balance
    if (before is None or after is None
            or base_runway.runway_status == "insufficient_data"
            or follow_runway.runway_status == "insufficient_data"):
        return ActionOutcome(
            recommendation_id=recommendation_id, recommendation_type=rec,
            action_reported_on=action_date, status="insufficient_data",
            metric="minimum_projected_balance", direction="higher_is_better",
            baseline=baseline, follow_up=follow_up,
            interpretation="insufficient_data", evidence_quality="limited",
            evidence=evidence,
            limitations=_limitations(
                "The authoritative runway is not available at one or both observation points.",
                "No partial account sum or invented cash position is substituted."))
    status = _classify(before, after, "higher_is_better")
    return ActionOutcome(
        recommendation_id=recommendation_id, recommendation_type=rec,
        action_reported_on=action_date, status=status,
        metric="minimum_projected_balance", direction="higher_is_better",
        baseline=baseline, follow_up=follow_up,
        baseline_value=money(before), follow_up_value=money(after),
        absolute_change=money(after - before),
        percentage_change=_percentage_change(before, after),
        interpretation=_interpretation(status, "higher_is_better"),
        evidence_quality="estimated", evidence=evidence,
        limitations=_limitations(
            "Cash values are forward-looking runway projections anchored on the action date and the observation date.",
            "Projections use current allocation state and monthly historical resolution, not stored historical forecasts.",
            "A higher projected minimum does not prove that the reported action produced it."))


def _obligation_outcome(db: Session, user_id: int, recommendation_id: str,
                        rec: CoachingType, action_date: date, as_of: date,
                        current, action_at: datetime) -> ActionOutcome:
    baseline, follow_up, elapsed = _windows(action_date, as_of)
    ids = _obligation_ids(recommendation_id, current)
    evidence = OutcomeEvidence()
    if not ids:
        return ActionOutcome(
            recommendation_id=recommendation_id, recommendation_type=rec,
            action_reported_on=action_date, status="insufficient_data",
            metric="obligation_remaining", direction="lower_is_better",
            baseline=baseline, follow_up=follow_up,
            interpretation="insufficient_data", evidence_quality="limited",
            evidence=evidence,
            limitations=_limitations(
                "The obligation identifier in this recommendation cannot be resolved safely.",
                "Aggregated or hashed obligation sets are not reconstructed."))
    items = db.query(ScheduledCashflowItem).filter(
        ScheduledCashflowItem.user_id == user_id,
        ScheduledCashflowItem.id.in_(ids),
    ).order_by(ScheduledCashflowItem.id).all()
    if len(items) != len(ids):
        return ActionOutcome(
            recommendation_id=recommendation_id, recommendation_type=rec,
            action_reported_on=action_date, status="insufficient_data",
            metric="obligation_remaining", direction="lower_is_better",
            baseline=baseline, follow_up=follow_up,
            interpretation="insufficient_data", evidence_quality="limited",
            evidence=evidence,
            limitations=_limitations(
                "One or more obligations from this recommendation no longer exist for this user."))
    observation_end = datetime.combine(min(as_of, action_date + timedelta(days=OBSERVATION_DAYS)),
                                       time.max, tzinfo=DHAKA)
    amounts = obligation_amounts_for_items(db, user_id, items, as_of=observation_end)
    baseline_amounts = obligation_amounts_for_items(db, user_id, items, as_of=action_at)
    before = sum((baseline_amounts[item.id].remaining_amount for item in items), ZERO)
    baseline = OutcomeWindow(start=action_date, end=action_date, days=1, is_complete=True)
    original = sum((amounts[item.id].original_amount for item in items), ZERO)
    allocated = sum((amounts[item.id].allocated_amount for item in items), ZERO)
    remaining = sum((amounts[item.id].remaining_amount for item in items), ZERO)
    evidence.obligations = [
        OutcomeObligation(
            item_id=item.id, title=item.title, due_date=item.due_date,
            status=item.status,
            original_amount=amounts[item.id].original_amount,
            allocated_amount=amounts[item.id].allocated_amount,
            remaining_amount=amounts[item.id].remaining_amount)
        for item in items
    ]
    subject = ", ".join(item.title for item in items) or None
    if elapsed < MIN_FOLLOW_UP_DAYS:
        return _pending(recommendation_id, rec, subject, action_date, baseline,
                        follow_up, "obligation_remaining", "lower_is_better", evidence,
                        ["Only %d elapsed day(s) are available." % max(0, elapsed)],
                        quality="recorded")
    settlement = ("fully_settled" if remaining == ZERO and original > ZERO
                  else "partially_settled" if allocated > ZERO and remaining > ZERO
                  else "not_settled")
    status = _classify(before, remaining, "lower_is_better")
    interpretation = {
        "fully_settled": "obligation_settled",
        "partially_settled": "obligation_partially_settled",
        "not_settled": "obligation_not_settled",
    }[settlement]
    return ActionOutcome(
        recommendation_id=recommendation_id, recommendation_type=rec,
        subject=subject, action_reported_on=action_date, status=status,
        metric="obligation_remaining", direction="lower_is_better",
        baseline=baseline, follow_up=follow_up,
        baseline_value=money(before), follow_up_value=money(remaining),
        absolute_change=money(remaining - before),
        percentage_change=_percentage_change(before, remaining),
        settlement_status=settlement, interpretation=interpretation,
        evidence_quality="recorded", evidence=evidence,
        limitations=_limitations(
            "Obligation values come from the existing AI-15B/AI-15C reconciliation; this layer performs no settlement arithmetic.",
            "Allocation history is evaluated at the action timestamp and follow-up end; principal uses the current recorded obligation amount.",
            "A confirmed allocation is user payment metadata, not an additional transaction."))


def _goal_outcome(db: Session, user_id: int, recommendation_id: str,
                  rec: CoachingType, action_date: date, as_of: date,
                  current) -> ActionOutcome:
    baseline, follow_up, _ = _windows(action_date, as_of)
    goal = _goal_for_outcome(db, user_id, recommendation_id, current)
    return ActionOutcome(
        recommendation_id=recommendation_id, recommendation_type=rec,
        subject=goal.name if goal is not None else None,
        action_reported_on=action_date, status="insufficient_data",
        metric="goal_saved_amount", direction="higher_is_better",
        baseline=baseline, follow_up=follow_up,
        interpretation="goal_history_unavailable", evidence_quality="limited",
        evidence=OutcomeEvidence(),
        limitations=_limitations(
            "Goal savings are user-reported and historical contribution amounts are not stored.",
            "A before/after goal change cannot be established from the existing authoritative data.",
            "No contribution or goal value is invented for this outcome."))


def _build_outcome(db: Session, user_id: int, row: CoachingFeedback,
                   as_of: date, current) -> ActionOutcome | None:
    recommendation_id = row.recommendation_id
    rec_type = recommendation_id.split(":", 1)[0]
    if rec_type not in COACHING_TYPES:
        return None
    action_date = _dhaka_date(row.updated_at or row.created_at)
    if action_date > as_of:
        return None
    current_item = current.get(recommendation_id)
    subject = current_item.subject if current_item is not None else None
    if rec_type in {"spending_spike", "repeated_spending"}:
        return _spending_outcome(db, user_id, recommendation_id, rec_type,
                                 subject, action_date, as_of, current_item)
    if rec_type == "savings_opportunity":
        return _savings_outcome(db, user_id, recommendation_id, rec_type,
                                action_date, as_of)
    if rec_type == "cash_risk":
        return _cash_outcome(db, user_id, recommendation_id, rec_type,
                             action_date, as_of)
    if rec_type == "upcoming_obligations":
        return _obligation_outcome(db, user_id, recommendation_id, rec_type,
                                   action_date, as_of, current_item, row.updated_at or row.created_at)
    return _goal_outcome(db, user_id, recommendation_id, rec_type,
                         action_date, as_of, current_item)


def action_outcomes(db: Session, user_id: int, *, as_of: date | None = None,
                    recommendation_id: str | None = None,
                    status: str | None = None) -> ActionOutcomeReport:
    """Derive observable outcomes for this user's acted-on recommendations."""
    if user_id <= 0:
        raise ValueError("Invalid outcome scope")
    as_of = as_of or today_dhaka()
    rows = db.query(CoachingFeedback).filter_by(
        user_id=user_id, status="acted_on").all()
    if recommendation_id is not None:
        rows = [row for row in rows if row.recommendation_id == recommendation_id]
        if not rows:
            raise HTTPException(404, "Action outcome not found")

    generated = financial_coaching(db, user_id, as_of=as_of) if rows else None
    current = ({item.id: item for item in generated.recommendations}
               if generated is not None else {})
    items = [item for row in rows
             if (item := _build_outcome(db, user_id, row, as_of, current)) is not None]
    if status is not None:
        items = [item for item in items if item.status == status]
    items.sort(key=lambda item: (-item.action_reported_on.toordinal(),
                                 item.recommendation_id))
    counts = {name: sum(item.status == name for item in items)
              for name in ("improved", "unchanged", "worsened", "pending", "insufficient_data")}
    return ActionOutcomeReport(
        as_of_date=as_of, items=items,
        summary=ActionOutcomeSummary(tracked=len(items), **counts),
        limitations=list(REPORT_LIMITATIONS))
