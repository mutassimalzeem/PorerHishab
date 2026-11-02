"""Versioned decisions over engine outputs; no queries, LLM, clocks or arithmetic.

The caller must supply the same authenticated user's feedback-visible coaching,
goal overview and health profile. This module is an internal computation layer,
not an authorization boundary or a replacement for FinancialCoachValidator.
"""
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from app.schemas.coaching import FinancialCoaching
from app.schemas.financial_coach import CoachAction, CoachEvidence, CoachIntent, CoachWarning, EvidenceType
from app.schemas.financial_health import FinancialHealthProfile
from app.schemas.financial_plan import FinancialPlan
from app.schemas.goal_planning import GoalPlanningOverview
from app.services.finance.action_plan import TYPE_RANK, plan_from_coaching
from app.services.finance.coaching import PRIORITY
from app.services.finance.financial_coach_evidence import EvidencePackage

VERSION = "ai-16a-v1"
LIMITATIONS = [
    "Planning decisions are interpretations of supplied engine outputs, not executed payments or guarantees.",
    "Goal allocations share the existing AI-15P capacity; action amounts are not additional monthly savings.",
    "Emergency reserve review does not establish essential expenses, a reserve target or a funding timeline.",
    "Debt interest, essential spending classification and long-term investment rules are unavailable; none are inferred.",
]


def _negative_numeric_fact(value: Decimal | int | str) -> bool:
    """Read existing evidence, including Decimal strings restored from JSON."""
    try:
        number = Decimal(value)
    except InvalidOperation:
        return False
    return number.is_finite() and number < 0


def build_financial_plan(
    coaching: FinancialCoaching,
    *,
    goal_planning: GoalPlanningOverview | None = None,
    financial_health: FinancialHealthProfile | None = None,
) -> FinancialPlan:
    """Compose a deterministic plan from same-date, tenant-scoped engine results.

    Existing critical/high urgency wins. Within urgency, preserve cash risk,
    obligations, reserve review, goals, category review, then savings ordering.
    AI-15P remains authoritative for accepted commitments and shared allocations;
    health liquidity watch/strained triggers review only, never a new amount.
    """
    day = coaching.as_of_date
    horizon = coaching.period
    if horizon.start != day or not 0 <= (horizon.end - day).days <= 366:
        raise ValueError("Invalid planning horizon")
    if goal_planning is not None and goal_planning.capacity.as_of_date != day:
        raise ValueError("Goal capacity date must match coaching")
    if financial_health is not None and financial_health.as_of_date != day:
        raise ValueError("Health date must match coaching")
    ids = [item.id for item in coaching.recommendations]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate recommendation IDs")
    if goal_planning is not None:
        ids = [g.goal_id for g in goal_planning.goals]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate goal IDs")
    if financial_health is not None:
        keys = [c.key for c in financial_health.components]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate health component keys")

    current = [r for r in coaching.recommendations if r.as_of_date == day and r.valid_until >= day]
    warnings = []
    if len(current) != len(coaching.recommendations):
        warnings.append(CoachWarning(code="STALE_RECOMMENDATIONS", message="Outdated recommendations were excluded; refresh source services."))
    # Deep copies prevent plan or adapter consumers from mutating the source facts.
    visible = coaching.model_copy(update={"recommendations": current}).model_copy(deep=True)
    base = plan_from_coaching(visible)
    evidence = []
    ranked = []
    limitations = list(base.limitations) + LIMITATIONS

    def add_evidence(key, source, label, value, kind):
        item = CoachEvidence(evidence_id=key, evidence_type=kind, source=source,
                             label=label, value=value, as_of_date=day)
        evidence.append(item)
        return key

    by_id = {r.id: r for r in current}
    for action in base.actions:
        rec = by_id[action.recommendation_id]
        token = sha256(rec.id.encode()).hexdigest()
        eid = add_evidence(f"ev_plan_recommendation_{token}", rec.source, rec.title,
                           {"amount": rec.amount, "evidence": rec.evidence.model_dump(mode="python")},
                           EvidenceType.DERIVED_FACT if rec.evidence_quality == "recorded" else EvidenceType.ESTIMATE)
        decision = CoachAction(action_id=rec.id, title=rec.title, description=rec.recommended_action,
                               priority=PRIORITY[rec.priority] + 1, evidence_ids=[eid])
        ranked.append(((decision.priority, TYPE_RANK[rec.type] * 2, rec.id), decision))
        limitations.extend(rec.limitations)

    if financial_health is None:
        limitations.append("Financial health is unavailable; emergency reserve adequacy is unknown.")
    else:
        limitations.extend(financial_health.limitations)
        for comp in sorted(financial_health.components, key=lambda c: c.key):
            if comp.key == "cashflow_stability" and comp.data_available:
                margins = [e for e in comp.evidence if e.metric == "mean_surplus_margin"
                           and _negative_numeric_fact(e.value)]
                if margins:
                    eid = add_evidence("ev_plan_negative_cashflow", "financial_health", comp.explanation,
                                       comp.model_dump(mode="python"), EvidenceType.DERIVED_FACT)
                    decision = CoachAction(action_id="plan:negative_cashflow", title="Address negative recorded cashflow",
                                           description="Review recorded income and spending before committing to additional savings.",
                                           priority=1, evidence_ids=[eid])
                    ranked.append(((1, 1, decision.action_id), decision))
                    limitations.extend(comp.limitations)
            if comp.key != "liquidity" or not comp.data_available or comp.status not in {"watch", "strained"} or not comp.evidence:
                continue
            # Liquidity uses historical runway reserves, so retain estimate semantics.
            eid = add_evidence("ev_plan_liquidity", "financial_health", comp.explanation,
                               comp.model_dump(mode="python"), EvidenceType.ESTIMATE)
            decision = CoachAction(action_id="plan:emergency_reserve", title="Review emergency reserves",
                                   description="Review verified cash and the existing runway reserve before assigning optional savings.",
                                   priority=2, evidence_ids=[eid])
            ranked.append(((2, 3, decision.action_id), decision))
            limitations.extend(comp.limitations)

    if goal_planning is None:
        limitations.append("Goal planning is unavailable; monthly allocations and goal timelines are unknown.")
    else:
        capacity = goal_planning.capacity
        limitations.extend(capacity.limitations)
        limitations.extend(capacity.explanations)
        if capacity.status == "insufficient_data":
            warnings.append(CoachWarning(code="UNKNOWN_PLANNING_CAPACITY", message="Planning capacity is unavailable; no funded goal allocation is established."))
        if goal_planning.over_capacity:
            warnings.append(CoachWarning(code="GOAL_OVER_CAPACITY", message="Accepted goal commitments exceed current capacity; review existing plans."))
        if any(r.type == "cash_risk" for r in current) or any(d.action_id == "plan:negative_cashflow" for _, d in ranked):
            warnings.append(CoachWarning(code="CASH_RISK_BEFORE_GOALS", message="Resolve cash risk before acting on optional goal proposals; the embedded overview is source context."))
        for goal in sorted(goal_planning.goals, key=lambda g: (g.priority, g.goal_id)):
            if goal.goal_status != "active":
                continue
            eid = add_evidence(f"ev_plan_goal_{goal.goal_id}", "goal_planning.overview", "Existing shared-pool goal proposal",
                               {"goal": goal.model_dump(mode="python"), "capacity": capacity.model_dump(mode="python")}, EvidenceType.ESTIMATE)
            decision = CoachAction(action_id=f"plan:goal:{goal.goal_id}", title="Review the existing goal plan",
                                   description=goal.explanation, priority=3, evidence_ids=[eid])
            ranked.append(((3, 4, f"{goal.priority}:{goal.goal_id:020d}"), decision))

    priorities = [decision for _, decision in sorted(ranked, key=lambda pair: pair[0])]
    # Explicit interpretation provenance separates decisions from supporting facts.
    if priorities:
        policy_id = add_evidence("ev_plan_policy", "financial_planner", "Versioned priority interpretation",
                                 {"planner_version": VERSION, "ordered_action_ids": [p.action_id for p in priorities]}, EvidenceType.INTERPRETATION)
        for decision in priorities:
            decision.evidence_ids.append(policy_id)
    status = base.data_status
    if status == "insufficient_data" and ((goal_planning is not None and goal_planning.capacity.status == "sufficient") or
                                           (financial_health is not None and any(c.data_available for c in financial_health.components))):
        status = "partial"
    if status == "sufficient" and (goal_planning is None or goal_planning.capacity.status == "insufficient_data" or financial_health is None or financial_health.status == "insufficient_data" or financial_health.missing_components or warnings):
        status = "partial"
    return FinancialPlan(**base.model_dump(exclude={"limitations", "data_status"}),
                         data_status=status, planning_horizon=horizon.model_copy(deep=True),
                         priorities=priorities, goal_planning=goal_planning.model_copy(deep=True) if goal_planning else None,
                         financial_health=financial_health.model_copy(deep=True) if financial_health else None,
                         evidence=evidence, warnings=warnings,
                         limitations=list(dict.fromkeys(limitations)))


def plan_evidence_package(plan: FinancialPlan) -> EvidencePackage:
    """Export only produced evidence for the existing Coach validation pipeline.

    Future explanation code must pass this package to FinancialCoachValidator;
    this adapter neither generates nor approves an LLM response.
    """
    return EvidencePackage(intent=CoachIntent.GOAL_PLANNING, as_of_date=plan.as_of_date,
                           evidence=[e.model_copy(deep=True) for e in plan.evidence],
                           limitations=list(plan.limitations),
                           missing_data=[] if plan.data_status == "sufficient" else ["complete_planning_context"],
                           period_start=plan.planning_horizon.start, period_end=plan.planning_horizon.end)
