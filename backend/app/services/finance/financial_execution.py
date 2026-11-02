"""AI-16C deterministic execution sequencing over AI-16B decisions."""
from app.schemas.financial_execution import (
    ExecutionKind,
    FinancialActionStep,
    FinancialExecutionPlan,
)
from app.schemas.financial_plan import FinancialDecisionSet, FinancialPriority


_KIND_BY_CATEGORY: dict[str, ExecutionKind] = {
    "cashflow_risk": "review_cashflow",
    "obligation_pressure": "review_obligations",
    "liquidity_risk": "review_liquidity",
    "capacity_review": "review_capacity",
    "goal_commitment": "review_goal_commitment",
    "goal_review": "review_goal",
    "spending_review": "review_spending",
    "savings_opportunity": "review_savings",
}

_TITLE_BY_KIND: dict[ExecutionKind, str] = {
    "review_cashflow": "Review cashflow constraint",
    "review_obligations": "Review upcoming obligations",
    "review_liquidity": "Review available reserves",
    "review_capacity": "Review goal capacity",
    "review_goal_commitment": "Review accepted goal commitment",
    "review_goal": "Review goal plan",
    "review_spending": "Review spending contributing to the issue",
    "review_savings": "Review savings opportunity",
}


def _description(priority: FinancialPriority, kind: ExecutionKind) -> str:
    if kind == "review_cashflow":
        return "Review the recorded cashflow constraint before considering optional financial actions."
    if kind == "review_obligations":
        return "Review known obligations and their existing commitments before changing optional plans."
    if kind == "review_liquidity":
        return "Review reserve and liquidity signals before committing funds elsewhere."
    if kind == "review_capacity":
        return "Review available goal capacity and resolve any capacity uncertainty before adding optional commitments."
    if kind == "review_goal_commitment":
        return "Review this accepted commitment without automatically reducing, cancelling, or reallocating it."
    if kind == "review_goal":
        return "Review the existing goal plan and its feasibility using the preserved planning evidence."
    if kind == "review_spending":
        return "Review the spending signal identified by the deterministic financial engines before acting on savings suggestions."
    return "Review the recorded savings opportunity only after its blocking priorities have been addressed."


def build_financial_execution_plan(decisions: FinancialDecisionSet) -> FinancialExecutionPlan:
    """Turn ordered AI-16B priorities into review steps; never execute money movement."""
    # Reuse upstream validation for mutable inputs, rather than duplicating its rules.
    source = FinancialDecisionSet.model_validate(decisions.model_dump(mode="python"))
    steps: list[FinancialActionStep] = []
    for sequence, priority in enumerate(source.priorities, start=1):
        kind = _KIND_BY_CATEGORY[priority.category]
        blocked = bool(priority.blocking_priority_ids or priority.blocking_factors)
        steps.append(
            FinancialActionStep(
                step_id=f"step_{sequence}_{priority.priority_id}",
                priority_id=priority.priority_id,
                sequence=sequence,
                kind=kind,
                level=priority.level,
                title=_TITLE_BY_KIND[kind],
                description=_description(priority, kind),
                source_action_ids=list(priority.source_action_ids),
                evidence_ids=list(priority.evidence_ids),
                blocking_priority_ids=list(priority.blocking_priority_ids),
                blocking_factors=list(priority.blocking_factors),
                state="blocked" if blocked else "ready",
                assumptions=list(priority.assumptions),
                limitations=list(priority.limitations),
            )
        )

    return FinancialExecutionPlan(
        source_decision_version=source.policy_version,
        as_of_date=source.as_of_date,
        planning_horizon=source.planning_horizon,
        data_status=source.data_status,
        steps=steps,
        evidence=[item.model_copy(deep=True) for item in source.evidence],
        warnings=[item.model_copy(deep=True) for item in source.warnings],
        limitations=list(source.limitations),
    )
