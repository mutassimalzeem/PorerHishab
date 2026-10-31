"""Read-only prioritization over AI-15G visibility. No financial calculations."""
from app.schemas.action_plan import CoachingAction, CoachingActionPlan, CompletedActionFeedback
from app.services.finance.coaching import PRIORITY
from app.services.finance.coaching_feedback import visible_coaching

MAX_ACTIVE_ACTIONS = 5
TYPE_RANK = {"cash_risk": 0, "upcoming_obligations": 1, "goal_risk": 2,
             "spending_spike": 3, "repeated_spending": 3, "savings_opportunity": 4}
LIMIT_NOTE = "The plan shows the first five active actions, or all critical actions if there are more than five; review coaching for other recommendations."
COMPLETION_NOTE = "Reported done means the user reported completion; no financial action has been verified."


def action_plan(db, user_id, *, priority=None, **kwargs):
    # Generate once without a priority filter so completion scope remains consistent.
    coaching = visible_coaching(db, user_id, **kwargs)
    ordered = sorted((item for item in coaching.recommendations
                      if priority is None or item.priority == priority),
                     key=lambda item: (PRIORITY[item.priority], TYPE_RANK[item.type], item.id))
    # Preserve every critical warning even if future rules emit more than five.
    limit = max(MAX_ACTIVE_ACTIONS, sum(item.priority == "critical" for item in ordered))
    selected = ordered[:limit]
    actions = [CoachingAction(**item.model_dump(include=set(CoachingAction.model_fields) - {"rank", "recommendation_id", "status"}),
                              recommendation_id=item.id, rank=rank)
               for rank, item in enumerate(selected, 1)]
    # Stale acted_on rows are history, never current completion or active advice.
    completed = [CompletedActionFeedback(**row.model_dump()) for row in coaching.feedback
                 if row.status == "acted_on" and row.is_current]
    completed.sort(key=lambda row: row.recommendation_id)
    limitations = list(coaching.limitations) + [COMPLETION_NOTE]
    if len(ordered) > len(selected):
        limitations.append(LIMIT_NOTE)
    return CoachingActionPlan(as_of_date=coaching.as_of_date, data_status=coaching.data_status,
        actions=actions, completed_feedback=completed, active_count=len(actions),
        completed_count=len(completed), assumptions=[], limitations=limitations)
