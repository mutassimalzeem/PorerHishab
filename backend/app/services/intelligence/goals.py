"""Goal progress assessment shared by the engine and the coach (AI-13).

This is the exact arithmetic the coach's ``goal_plan`` has always exposed,
extracted so the engine and the presentation layer share one source of
truth. Contribution amounts are derived figures (rounding up), affordability
is an estimate based on historical surplus and scheduled obligations, and
saved amounts are always user-reported.

Returns a structured assessment; ``coach.goal_plan`` layers its own response
fields on top without recomputing anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_UP

from sqlalchemy.orm import Session

from app.models.savings_goal import SavingsGoal
from app.services.intelligence.facts import scheduled_totals
from app.services.intelligence.periods import money, month_shift

ZERO = Decimal("0.00")

AFFORDABILITY_UNKNOWN = "unknown"
AFFORDABILITY_FEASIBLE = "appears_feasible"
AFFORDABILITY_AT_RISK = "at_risk"
AFFORDABILITY_COMPLETED = "completed"
AFFORDABILITY_CANCELLED = "cancelled"
AFFORDABILITY_OVERDUE = "overdue"

UNKNOWN_SAVINGS_LIMITATION = (
    "Current goal savings are unknown; report them explicitly to calculate contributions."
)
INADEQUATE_HISTORY_LIMITATION = (
    "Three complete calendar months with observed records are needed to estimate affordability."
)
OTHER_GOAL_UNKNOWN_SAVINGS_LIMITATION = (
    "Another active goal has unknown savings, so shared affordability cannot be assessed."
)


@dataclass(frozen=True)
class GoalAssessment:
    """Deterministic affordability view of one savings goal."""

    goal: SavingsGoal
    as_of: date
    remaining: Decimal | None          # None when current savings are unknown
    required_monthly: Decimal | None   # derived contribution estimate
    capacity: Decimal | None           # estimated monthly capacity (estimate)
    affordability: str
    limitations: list[str]

    @property
    def is_concerning(self) -> bool:
        return self.affordability in {AFFORDABILITY_AT_RISK, AFFORDABILITY_OVERDUE}

    def to_dict(self) -> dict:
        return {
            "as_of_date": self.as_of.isoformat(),
            "remaining_amount": None if self.remaining is None else str(self.remaining),
            "required_monthly": None if self.required_monthly is None
            else str(self.required_monthly),
            "estimated_monthly_capacity": None if self.capacity is None
            else str(self.capacity),
            "affordability": self.affordability,
            "limitations": list(self.limitations),
        }


def goal_assessment(
    db: Session,
    user_id: int,
    goal: SavingsGoal,
    as_of: date,
    history: dict | None,
) -> GoalAssessment:
    """Assess affordability with the original coach arithmetic, unchanged.

    ``history`` is the coach-shaped history payload
    (``{"adequate": ..., "baseline": {"average_monthly_income": ...,
    "average_monthly_expenses": ...}}``); when omitted the caller must not
    expect a capacity estimate.
    """
    remaining = (
        money(max(ZERO, goal.target_amount - goal.current_saved))
        if goal.current_saved is not None else None
    )
    months = max(
        1,
        (goal.target_date.year - as_of.year) * 12
        + goal.target_date.month - as_of.month + 1,
    )
    required_monthly = (
        (remaining / months).quantize(Decimal("0.01"), rounding=ROUND_UP)
        if remaining is not None else None
    )

    capacity = None
    limitations: list[str] = []
    if history is not None and history.get("adequate"):
        next_end = month_shift(as_of, 1) - timedelta(days=1)
        obligations, _ = scheduled_totals(db, user_id, as_of, next_end)
        baseline = history["baseline"]
        capacity = money(
            baseline["average_monthly_income"]
            - max(baseline["average_monthly_expenses"], obligations))
        others = db.query(SavingsGoal).filter(
            SavingsGoal.user_id == user_id,
            SavingsGoal.status == "active",
            SavingsGoal.id != goal.id,
        ).all()
        for other in others:
            if other.current_saved is None:
                capacity = None
                limitations.append(OTHER_GOAL_UNKNOWN_SAVINGS_LIMITATION)
                break
            other_months = max(
                1,
                (other.target_date.year - as_of.year) * 12
                + other.target_date.month - as_of.month + 1,
            )
            shared = max(ZERO, other.target_amount - other.current_saved)
            capacity -= (shared / other_months).quantize(
                Decimal("0.01"), rounding=ROUND_UP)

    status = AFFORDABILITY_UNKNOWN
    if goal.status == "cancelled":
        status = AFFORDABILITY_CANCELLED
    elif remaining == 0:
        status = AFFORDABILITY_COMPLETED
    elif goal.target_date < as_of:
        status = AFFORDABILITY_OVERDUE
    elif required_monthly is not None and capacity is not None:
        status = AFFORDABILITY_FEASIBLE if capacity >= required_monthly \
            else AFFORDABILITY_AT_RISK

    if remaining is None:
        limitations.append(UNKNOWN_SAVINGS_LIMITATION)
    if history is None or not history.get("adequate"):
        limitations.append(INADEQUATE_HISTORY_LIMITATION)

    return GoalAssessment(
        goal=goal,
        as_of=as_of,
        remaining=remaining,
        required_monthly=required_monthly,
        capacity=capacity,
        affordability=status,
        limitations=limitations,
    )
