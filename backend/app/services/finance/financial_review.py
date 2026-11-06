"""Owner-scoped runtime composition; no writes, new calculations or policies."""
from datetime import date, datetime
from app.schemas.financial_review import FinancialReview
from app.services.finance.coaching_feedback import visible_coaching
from app.services.finance.goal_planning import planning_overview
from app.services.finance.financial_health import gather_profile
from app.services.finance.financial_planner import build_financial_plan
from app.services.finance.financial_prioritization import prioritize_financial_plan
from app.services.finance.financial_execution import build_financial_execution_plan
from app.services.intelligence.periods import today_dhaka

LIMITATIONS = [
    "Review only: no payment, transfer, allocation or goal change has been executed. Use existing explicit mutation endpoints with user confirmation.",
    "Coaching source selection retains five actions or all critical actions; this review is not an exhaustive inventory of financial issues.",
    "As-of dates select financial windows over current records, not a reconstruction of historical account, goal or feedback versions.",
    "Source services perform separate reads in the request transaction; this response does not establish an atomic ledger snapshot.",
]


def financial_review(db, user_id: int, *, as_of: date | None = None,
                     schedules_confirmed: bool = False,
                     observed_at: datetime | None = None) -> FinancialReview:
    """The API supplies user_id exclusively from its authenticated dependency.

    observed_at is the health observation timestamp, injectable for offline replay.
    Monetary values, missing-data states and blockers remain owned by AI-15/16.
    """
    if user_id <= 0:
        raise ValueError("Invalid review scope")
    day = as_of or today_dhaka()
    if not date(1900, 1, 1) <= day <= date(9998, 12, 31):
        raise ValueError("Unsupported review date")
    coaching = visible_coaching(db, user_id, as_of=day)
    goals = planning_overview(db, user_id, as_of=day, schedules_confirmed=schedules_confirmed)
    health = gather_profile(db, user_id, as_of=day, observed_at=observed_at)
    plan = build_financial_plan(coaching, goal_planning=goals, financial_health=health)
    plan.limitations = list(dict.fromkeys([*plan.limitations, *LIMITATIONS]))
    decisions = prioritize_financial_plan(plan)
    execution = build_financial_execution_plan(decisions)
    return FinancialReview(schedules_confirmed=schedules_confirmed, plan=plan,
                           decisions=decisions, execution_plan=execution)
