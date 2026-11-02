"""AI-16B issue prioritization over AI-16A; no financial calculations or I/O."""
from app.schemas.financial_coach import CoachEvidence, CoachIntent, CoachWarning, EvidenceType
from app.schemas.financial_plan import FinancialDecisionSet, FinancialPlan, FinancialPriority, PriorityConflict
from app.services.finance.financial_coach_evidence import EvidencePackage

# Ordinals express policy order, not financial scores or confidence estimates.
LEVEL_ORDER = {name: index for index, name in enumerate(("critical", "high", "medium", "low"))}
CATEGORY_ORDER = {name: index for index, name in enumerate((
    "cashflow_risk", "obligation_pressure", "liquidity_risk", "capacity_review",
    "goal_commitment", "goal_review", "spending_review", "savings_opportunity",
))}
QUALITY_ORDER = {name: index for index, name in enumerate(("recorded", "derived", "estimated", "limited"))}
SOURCE_LEVEL = {1: "critical", 2: "high", 3: "medium", 4: "low", 5: "low"}
SOURCE_CATEGORY = {
    "cash_risk": ("cashflow_risk", "cashflow_constraint"),
    "upcoming_obligations": ("obligation_pressure", "known_obligations"),
    "goal_risk": ("goal_review", "source_goal_risk"),
    "spending_spike": ("spending_review", "spending_increase"),
    "repeated_spending": ("spending_review", "spending_increase"),
    "savings_opportunity": ("savings_opportunity", "unassigned_savings"),
}
LIMITATIONS = [
    "Priority dependencies govern review and optional funding; they do not authorize delaying bills or cancelling accepted commitments.",
    "Review precedence is not proof of a funding deficit; conflicts do not create, transfer or reallocate money.",
    "The input must be assembled for one authenticated user; this pure service cannot verify tenant ownership.",
    "Only signals retained by AI-16A are available; omitted recommendations are not reconstructed.",
]


def prioritize_financial_plan(plan: FinancialPlan) -> FinancialDecisionSet:
    """Rank supported issues, preserving source urgency except explicit dependencies.

    Existing goal priority and evidence quality break ties within urgency/category. Stable IDs break remaining
    ties. Dependencies are evaluated first, using a deterministic topological order.
    """
    # Revalidate mutable Pydantic inputs, then work only on detached values.
    source = FinancialPlan.model_validate(plan.model_dump(mode="python"))
    day = source.as_of_date
    if any(e.as_of_date is not None and e.as_of_date != day for e in source.evidence):
        raise ValueError("Plan evidence date must match the planning date")
    evidence = {e.evidence_id: e for e in source.evidence}
    priority_by_id = {p.action_id: p for p in source.priorities}
    actions = {a.id: a for a in source.actions}
    if len(actions) != len(source.actions):
        raise ValueError("Duplicate source action IDs")
    overview = source.goal_planning
    goals = {g.goal_id: g for g in overview.goals} if overview else {}
    if overview and len(goals) != len(overview.goals):
        raise ValueError("Duplicate goal IDs")
    goal_priority_ids = {f"plan:goal:{gid}" for gid in goals}
    warnings = list(source.warnings)
    candidates: dict[str, FinancialPriority] = {}
    goal_signals = {}
    goal_order = {}

    def add(key, category, reason, title, level, refs, source_ids=(), assumptions=(), limitations=()):
        refs = sorted(set(refs))
        support = [evidence[eid] for eid in refs if evidence[eid].evidence_type != EvidenceType.INTERPRETATION]
        if not support:
            raise ValueError("Priority requires source engine evidence")
        if any(e.as_of_date != day for e in support):
            raise ValueError("Supporting evidence date must match the planning date")
        qualities = {EvidenceType.RAW_DATA: "recorded", EvidenceType.DERIVED_FACT: "derived", EvidenceType.ESTIMATE: "estimated"}
        quality = max((qualities[e.evidence_type] for e in support), key=QUALITY_ORDER.__getitem__)
        if any(actions[sid].evidence_quality == "limited" for sid in source_ids if sid in actions):
            quality = "limited"
        existing = candidates.get(key)
        if existing:
            existing.level = min((existing.level, level), key=LEVEL_ORDER.__getitem__)
            existing.evidence_ids = sorted(set(existing.evidence_ids + refs))
            existing.source_action_ids = sorted(set(existing.source_action_ids + list(source_ids)))
            existing.evidence_quality = max((existing.evidence_quality, quality), key=QUALITY_ORDER.__getitem__)
            existing.assumptions = sorted(set(existing.assumptions + list(assumptions)))
            existing.limitations = sorted(set(existing.limitations + list(limitations)))
        else:
            candidates[key] = FinancialPriority(
                priority_id=key, category=category, level=level, title=title, reason=reason,
                source_action_ids=sorted(set(source_ids)), evidence_ids=refs, evidence_quality=quality,
                assumptions=sorted(set(assumptions)), limitations=sorted(set(source.limitations + list(limitations))),
            )

    for item in sorted(source.priorities, key=lambda p: p.action_id):
        action = actions.get(item.action_id)
        if item.action_id == "plan:negative_cashflow":
            category, reason = "cashflow_risk", "cashflow_constraint"
        elif item.action_id == "plan:emergency_reserve":
            category, reason = "liquidity_risk", "liquidity_constraint"
        elif item.action_id.startswith("plan:goal:"):
            # Goal issues are handled from the embedded authoritative overview below.
            if item.action_id not in goal_priority_ids:
                raise ValueError("Goal priority has no corresponding goal overview item")
            continue
        elif action is not None:
            category, reason = SOURCE_CATEGORY[action.type]
        else:
            warnings.append(CoachWarning(code="UNSUPPORTED_PLAN_PRIORITY", message=f"Unsupported source priority excluded: {item.action_id}"))
            continue
        if action is not None and action.type == "goal_risk":
            goal_ids = set()
            for eid in item.evidence_ids:
                value = evidence[eid].value
                details = value.get("evidence") if isinstance(value, dict) else None
                gid = details.get("goal_id") if isinstance(details, dict) else None
                if isinstance(gid, int) and gid in goals and goals[gid].goal_status == "active":
                    goal_ids.add(gid)
            if len(goal_ids) == 1:
                goal_signals.setdefault(min(goal_ids), []).append(item)
                continue
        key = f"priority:{category}" if category != "goal_review" and category != "spending_review" else f"priority:{item.action_id}"
        add(key, category, reason, item.title, SOURCE_LEVEL[item.priority], item.evidence_ids,
            source_ids=[item.action_id], assumptions=action.assumptions if action else (),
            limitations=action.limitations if action else ())
        if category == "goal_review":
            candidates[key].blocking_factors.append("goal_capacity_unknown")

    if overview is not None:
        key = "ev_priority_goal_overview"
        if key in evidence:
            raise ValueError("Reserved prioritization evidence ID already exists")
        # Projection of an existing engine result, not a newly calculated fact.
        evidence[key] = CoachEvidence(evidence_id=key, evidence_type=EvidenceType.ESTIMATE,
                                      source="goal_planning.overview", label="Existing capacity and commitment constraints",
                                      value=overview.model_dump(mode="python"), as_of_date=day)
        capacity_known = overview.capacity.status == "sufficient" and overview.capacity.conservative_monthly_capacity is not None
        if not capacity_known and overview.goals:
            add("priority:capacity", "capacity_review", "capacity_unavailable", "Establish goal planning inputs", "high", [key])
        elif capacity_known and overview.over_capacity:
            add("priority:commitment_capacity", "goal_commitment", "commitments_exceed_capacity", "Review accepted commitments against capacity", "high", [key])
        for goal in sorted(overview.goals, key=lambda g: (g.priority, g.goal_id)):
            if goal.goal_status != "active":
                continue
            accepted = goal.accepted_monthly > 0
            category = "goal_commitment" if accepted else "goal_review"
            source_item = priority_by_id.get(f"plan:goal:{goal.goal_id}")
            refs = [key] + (source_item.evidence_ids if source_item else [])
            pid = f"priority:goal:{goal.goal_id}"
            add(pid, category, "accepted_commitment" if accepted else "active_goal",
                "Review an existing accepted goal commitment" if accepted else "Review an active goal",
                SOURCE_LEVEL[source_item.priority] if source_item else "medium", refs,
                source_ids=[source_item.action_id] if source_item else ())
            goal_order[pid] = (goal.priority, goal.goal_id)
            for signal in goal_signals.get(goal.goal_id, []):
                action = actions[signal.action_id]
                add(pid, category, "accepted_commitment" if accepted else "active_goal",
                    candidates[pid].title, SOURCE_LEVEL[signal.priority], signal.evidence_ids,
                    source_ids=[signal.action_id], assumptions=action.assumptions, limitations=action.limitations)
            if not accepted and (not capacity_known or goal.feasibility == "insufficient_data"):
                candidates[pid].blocking_factors.append("goal_capacity_unknown")
            if not accepted and goal.feasibility in {"not_currently_feasible", "challenging", "feasible_with_adjustments"}:
                candidates[pid].blocking_factors.append("goal_not_feasible")

    # Dependencies express constraints/review precedence, never changes to funding.
    conflicts = []
    candidates_by_id = sorted(candidates.values(), key=lambda p: p.priority_id)
    has_cashflow_risk = any(p.category == "cashflow_risk" for p in candidates_by_id)
    for deferred in candidates_by_id:
        optional = deferred.category in {"goal_review", "savings_opportunity"}
        for preceding in candidates_by_id:
            reason, kind = None, "review_precedence"
            if preceding.category == "cashflow_risk" and (optional or deferred.category == "spending_review"):
                reason = "stabilize_cashflow"
                kind = "funding_constraint" if optional else "review_precedence"
            elif preceding.category == "obligation_pressure" and (optional or deferred.category == "spending_review"):
                reason = "protect_obligations"
            elif preceding.category == "liquidity_risk" and optional:
                reason = "review_reserves"
            elif preceding.reason == "commitments_exceed_capacity" and optional:
                reason, kind = "resolve_capacity", "funding_constraint"
            elif preceding.category == "capacity_review" and optional:
                reason, kind = "resolve_capacity", "funding_constraint"
            elif preceding.reason == "accepted_commitment" and optional:
                reason = "review_accepted_commitments"
            elif preceding.category == "spending_review" and optional and has_cashflow_risk:
                reason = "review_spending_before_savings"
            if reason:
                deferred.blocking_priority_ids.append(preceding.priority_id)
                conflicts.append(PriorityConflict(preceding_priority_id=preceding.priority_id,
                                                  deferred_priority_id=deferred.priority_id, kind=kind, reason=reason))

    def order(item):
        return (LEVEL_ORDER[item.level], CATEGORY_ORDER[item.category],
                goal_order.get(item.priority_id, (0, 0)), QUALITY_ORDER[item.evidence_quality], item.priority_id)

    ordered = []
    pending = dict(candidates)
    emitted = set()
    while pending:
        ready = [p for p in pending.values() if set(p.blocking_priority_ids) <= emitted]
        if not ready:
            raise ValueError("Cyclic financial priority dependencies")
        item = min(ready, key=order)
        ordered.append(item)
        emitted.add(item.priority_id)
        del pending[item.priority_id]
    conflicts.sort(key=lambda c: (c.preceding_priority_id, c.deferred_priority_id))
    if "ev_priority_policy" in evidence:
        raise ValueError("Reserved prioritization evidence ID already exists")
    if ordered:
        evidence["ev_priority_policy"] = CoachEvidence(
            evidence_id="ev_priority_policy", evidence_type=EvidenceType.INTERPRETATION,
            source="financial_prioritization", label="Produced priority order and dependencies",
            value={"policy_version": "ai-16b-v1", "priorities": [p.model_dump(mode="python") for p in ordered],
                   "conflicts": [c.model_dump(mode="python") for c in conflicts]}, as_of_date=day,
        )
    status = source.data_status
    if status == "sufficient" and (warnings or any(p.blocking_factors for p in ordered)):
        status = "partial"
    return FinancialDecisionSet(
        as_of_date=day, planning_horizon=source.planning_horizon, data_status=status,
        priorities=ordered, conflicts=conflicts,
        evidence=[evidence[key] for key in sorted(evidence)], goal_planning=overview,
        warnings=warnings, limitations=list(dict.fromkeys(source.limitations + LIMITATIONS)),
    )


def decision_evidence_package(decisions: FinancialDecisionSet) -> EvidencePackage:
    """Export produced source evidence; future explanations still require AI-15S validation."""
    checked = FinancialDecisionSet.model_validate(decisions.model_dump(mode="python"))
    return EvidencePackage(intent=CoachIntent.GOAL_PLANNING, as_of_date=checked.as_of_date,
                           evidence=checked.evidence, limitations=checked.limitations,
                           missing_data=[] if checked.data_status == "sufficient" else ["complete_planning_context"],
                           period_start=checked.planning_horizon.start, period_end=checked.planning_horizon.end)
