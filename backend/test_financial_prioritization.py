"""AI-16B issue ordering, source provenance, constraints and pure computation."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D
import socket

import pytest
from pydantic import ValidationError

from app.schemas.financial_coach import CoachAction, CoachClaim, CoachIntent, CoachResponse, EvidenceType
from app.schemas.financial_plan import FinancialDecisionSet
from app.services.finance.financial_planner import build_financial_plan
from app.services.finance.financial_prioritization import prioritize_financial_plan, decision_evidence_package
from app.services.finance.financial_coach_validator import validate_coach_response
from app.services.finance.goal_planning import planning_overview, create_plan
from app.schemas.goal_planning import PlanRequest
from test_financial_planner import coaching, health
from test_goal_planning import data, seed, DAY  # noqa: F401


@pytest.fixture
def goals(data):
    db, users = data
    seed(db, users[0], target="10000.01", priority=5)
    seed(db, users[0], target="20000.02", priority=1)
    return planning_overview(db, users[0].id, schedules_confirmed=True, as_of=DAY)


def result(*kinds, overview=None, profile=None):
    return prioritize_financial_plan(build_financial_plan(coaching(*kinds), goal_planning=overview, financial_health=profile))


def find(decisions, category):
    return [p for p in decisions.priorities if p.category == category]


def test_no_signals_no_invented_priorities():
    decisions = result()
    assert decisions.priorities == decisions.conflicts == decisions.evidence == []
    assert decisions.policy_version == "ai-16b-v1"
    assert decisions.goal_planning is None


@pytest.mark.parametrize("kind,category", [("cash_risk", "cashflow_risk"), ("upcoming_obligations", "obligation_pressure"), ("repeated_spending", "spending_review"), ("savings_opportunity", "savings_opportunity")])
def test_one_source_issue(kind, category):
    decisions = result(kind)
    assert len(decisions.priorities) == 1
    assert decisions.priorities[0].category == category
    assert decisions.priorities[0].source_action_ids
    assert decisions.conflicts == []


def test_cashflow_blocks_goals_and_optional_savings(goals):
    decisions = result("cash_risk", "savings_opportunity", overview=goals)
    cash = decisions.priorities[0]
    assert cash.category == "cashflow_risk"
    for item in find(decisions, "goal_review") + find(decisions, "savings_opportunity"):
        assert cash.priority_id in item.blocking_priority_ids
        conflict = next(c for c in decisions.conflicts if c.preceding_priority_id == cash.priority_id and c.deferred_priority_id == item.priority_id)
        assert conflict.kind == "funding_constraint" and conflict.reason == "stabilize_cashflow"


def test_obligations_before_category_decisions_and_optional_savings():
    decisions = result("savings_opportunity", "repeated_spending", "upcoming_obligations")
    obligation = decisions.priorities[0]
    assert obligation.category == "obligation_pressure"
    for item in decisions.priorities[1:]:
        assert obligation.priority_id in item.blocking_priority_ids
    assert all(c.kind == "review_precedence" for c in decisions.conflicts)


def test_liquidity_before_optional_goal_acceleration(goals):
    decisions = result(overview=goals, profile=health())
    reserve = decisions.priorities[0]
    assert reserve.category == "liquidity_risk"
    assert all(reserve.priority_id in p.blocking_priority_ids for p in find(decisions, "goal_review"))
    assert all(c.reason == "review_reserves" for c in decisions.conflicts)


def test_negative_cashflow_and_runway_coalesce_without_double_counting():
    profile = health("strong")
    comp = profile.components[0]
    comp.key = "cashflow_stability"
    comp.evidence[0].metric = "mean_surplus_margin"
    comp.evidence[0].value = D("-0.25")
    decisions = result("cash_risk", "repeated_spending", "savings_opportunity", profile=profile)
    cash = find(decisions, "cashflow_risk")
    assert len(cash) == 1
    assert set(cash[0].source_action_ids) == {"cash_risk:cash_risk", "plan:negative_cashflow"}
    spending = find(decisions, "spending_review")[0]
    savings = find(decisions, "savings_opportunity")[0]
    assert cash[0].priority_id in spending.blocking_priority_ids
    assert spending.priority_id in savings.blocking_priority_ids


def test_accepted_commitment_stays_authoritative_and_precedes_new_goals(data):
    db, users = data
    goal = seed(db, users[0], target="10000.01", priority=5)
    seed(db, users[0], target="20000.02", priority=1)
    create_plan(db, users[0].id, goal.id, PlanRequest(idempotency_key="ai16b-accepted-plan", schedules_confirmed=True), as_of=DAY)
    overview = planning_overview(db, users[0].id, schedules_confirmed=True, as_of=DAY)
    before = overview.model_dump()
    decisions = result(overview=overview)
    commitment = decisions.priorities[0]
    assert commitment.category == "goal_commitment"
    assert commitment.reason == "accepted_commitment"
    assert commitment.priority_id in find(decisions, "goal_review")[0].blocking_priority_ids
    assert decisions.goal_planning.model_dump() == before
    assert decisions.goal_planning.upcoming_milestones == overview.upcoming_milestones
    assert decisions.goal_planning.goals[0].accepted_monthly == overview.goals[0].accepted_monthly
    assert overview.model_dump() == before


def test_over_capacity_blocks_additional_goals_without_reallocation(goals):
    goals.over_capacity = True
    decisions = result("savings_opportunity", overview=goals)
    constraint = next(p for p in decisions.priorities if p.reason == "commitments_exceed_capacity")
    assert constraint.level == "high"
    assert all(constraint.priority_id in p.blocking_priority_ids for p in find(decisions, "goal_review") + find(decisions, "savings_opportunity"))
    assert decisions.goal_planning == goals


def test_unknown_capacity_is_not_zero_and_conflicting_flag_is_not_promoted(goals):
    goals.capacity.status = "insufficient_data"
    goals.capacity.conservative_monthly_capacity = None
    goals.over_capacity = True
    decisions = result(overview=goals)
    unknown = find(decisions, "capacity_review")[0]
    assert unknown.reason == "capacity_unavailable"
    assert not any(p.reason == "commitments_exceed_capacity" for p in decisions.priorities)
    assert all("goal_capacity_unknown" in p.blocking_factors and unknown.priority_id in p.blocking_priority_ids for p in find(decisions, "goal_review"))
    assert decisions.goal_planning.capacity.conservative_monthly_capacity is None


def test_known_zero_capacity_remains_known(goals):
    goals.capacity.conservative_monthly_capacity = D("0.00")
    for goal in goals.goals:
        goal.feasibility = "not_currently_feasible"
    decisions = result(overview=goals)
    assert not find(decisions, "capacity_review")
    assert all("goal_not_feasible" in p.blocking_factors and "goal_capacity_unknown" not in p.blocking_factors for p in find(decisions, "goal_review"))
    assert decisions.goal_planning.capacity.conservative_monthly_capacity == D("0.00")


def test_goal_risk_without_overview_remains_unfunded_review():
    decisions = result("goal_risk")
    assert decisions.priorities[0].blocking_factors == ["goal_capacity_unknown"]
    assert decisions.goal_planning is None


def test_goal_risk_for_accepted_goal_is_merged_into_commitment(goals):
    goal = goals.goals[0]
    goal.accepted_monthly = D("100.01")
    source = coaching("goal_risk")
    source.recommendations[0].evidence.goal_id = goal.goal_id
    source.recommendations[0].priority = "high"
    decisions = prioritize_financial_plan(build_financial_plan(source, goal_planning=goals))
    item = next(p for p in find(decisions, "goal_commitment") if p.priority_id == f"priority:goal:{goal.goal_id}")
    assert item.level == "high"
    assert "goal_risk:goal_risk" in item.source_action_ids
    assert len(decisions.priorities) == len(goals.goals)


def test_goal_priority_preserved_before_stable_id(goals):
    decisions = result(overview=goals)
    expected = sorted(goals.goals, key=lambda g: (g.priority, g.goal_id))
    assert [p.priority_id for p in decisions.priorities] == [f"priority:goal:{g.goal_id}" for g in expected]


def test_quality_breaks_same_category_urgency_ties():
    source = coaching("repeated_spending")
    rec = source.recommendations[0]
    source.recommendations = [rec.model_copy(update={"id": "review:a", "evidence_quality": "estimated"}), rec.model_copy(update={"id": "review:z", "evidence_quality": "recorded"})]
    decisions = prioritize_financial_plan(build_financial_plan(source))
    assert [p.evidence_quality for p in decisions.priorities] == ["derived", "estimated"]
    source.recommendations[0].evidence_quality = "limited"
    assert prioritize_financial_plan(build_financial_plan(source)).priorities[-1].evidence_quality == "limited"


def test_source_evidence_metadata_and_decimal_values_are_preserved(goals):
    plan = build_financial_plan(coaching("savings_opportunity"), goal_planning=goals)
    original = plan.evidence[0]
    original.confidence = D("0.75")
    before = deepcopy(plan.model_dump())
    decisions = prioritize_financial_plan(plan)
    copied = next(e for e in decisions.evidence if e.evidence_id == original.evidence_id)
    assert copied.model_dump() == original.model_dump()
    assert copied.value["amount"] == D("123.45") and isinstance(copied.value["amount"], D)
    assert decisions.goal_planning.total_target_amount == D("30000.03")
    assert all(p.evidence_ids for p in decisions.priorities)
    assert plan.model_dump() == before
    assert FinancialDecisionSet.model_validate_json(decisions.model_dump_json()).model_dump_json() == decisions.model_dump_json()


@pytest.mark.parametrize("mutation", ["unknown_evidence", "duplicate_evidence", "wrong_evidence_date", "wrong_goal_date", "wrong_health_date", "unknown_support_date"])
def test_invalid_or_mixed_date_inputs_rejected(goals, mutation):
    plan = build_financial_plan(coaching("cash_risk"), goal_planning=goals, financial_health=health())
    if mutation == "unknown_evidence":
        plan.priorities[0].evidence_ids = ["invented"]
    elif mutation == "duplicate_evidence":
        plan.evidence.append(plan.evidence[0])
    elif mutation == "wrong_evidence_date":
        plan.evidence[0].as_of_date -= timedelta(days=1)
    elif mutation == "wrong_goal_date":
        plan.goal_planning.capacity.as_of_date -= timedelta(days=1)
    elif mutation == "wrong_health_date":
        plan.financial_health.as_of_date -= timedelta(days=1)
    else:
        plan.evidence[0].as_of_date = None
    with pytest.raises(ValueError):
        prioritize_financial_plan(plan)


@pytest.mark.parametrize("mutation", ["duplicate_evidence", "unknown_evidence", "cycle", "unknown_blocker", "unknown_conflict", "only_interpretation"])
def test_decision_contract_checks_evidence_and_graph_integrity(mutation):
    decisions = result("cash_risk", "savings_opportunity")
    payload = decisions.model_dump()
    if mutation == "duplicate_evidence":
        payload["evidence"].append(payload["evidence"][0])
    elif mutation == "unknown_evidence":
        payload["priorities"][0]["evidence_ids"] = ["fabricated"]
    elif mutation == "cycle":
        payload["priorities"][0]["blocking_priority_ids"] = [payload["priorities"][-1]["priority_id"]]
    elif mutation == "unknown_blocker":
        payload["priorities"][0]["blocking_priority_ids"] = ["absent"]
    elif mutation == "unknown_conflict":
        payload["conflicts"][0]["preceding_priority_id"] = "absent"
    else:
        payload["priorities"][0]["evidence_ids"] = ["ev_plan_policy"]
    with pytest.raises(ValidationError):
        FinancialDecisionSet.model_validate(payload)


def test_pure_deterministic_and_detached(monkeypatch, goals):
    from sqlalchemy.orm import Session
    from app.services.finance.financial_coach_generator import FinancialCoachGenerator
    plan = build_financial_plan(coaching("cash_risk", "repeated_spending", "savings_opportunity"), goal_planning=goals, financial_health=health())
    before = deepcopy(plan.model_dump())
    def forbidden(*args, **kwargs):
        pytest.fail("Prioritizer attempted I/O or LLM access")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(Session, "query", forbidden)
    monkeypatch.setattr(Session, "execute", forbidden)
    monkeypatch.setattr(FinancialCoachGenerator, "generate_response", forbidden)
    first = prioritize_financial_plan(plan)
    second = prioritize_financial_plan(plan)
    assert first.model_dump_json() == second.model_dump_json()
    first.evidence[0].label = "Changed"
    first.goal_planning.goals[0].accepted_monthly = D("999")
    first.priorities[0].limitations.append("Changed")
    assert plan.model_dump() == before
    package = decision_evidence_package(second)
    package.evidence[0].label = "Changed adapter"
    assert second.evidence[0].label != package.evidence[0].label


def test_unknown_source_signal_is_explicitly_excluded():
    plan = build_financial_plan(coaching("cash_risk"))
    plan.priorities.append(CoachAction(action_id="unknown:signal", title="Unknown", description="Unknown", evidence_ids=plan.priorities[0].evidence_ids))
    decisions = prioritize_financial_plan(plan)
    assert len(decisions.priorities) == 1
    assert any(w.code == "UNSUPPORTED_PLAN_PRIORITY" for w in decisions.warnings)


def test_coach_adapter_contains_actual_policy_and_rejects_invented_provenance():
    decisions = result("savings_opportunity")
    package = decision_evidence_package(decisions)
    policy = next(e for e in package.evidence if e.evidence_id == "ev_priority_policy")
    assert policy.evidence_type == EvidenceType.INTERPRETATION
    assert policy.value["priorities"][0]["priority_id"] == decisions.priorities[0].priority_id
    supporting = next(e for e in package.evidence if isinstance(e.value, dict) and e.value.get("amount") == D("123.45"))
    response = CoachResponse(intent=CoachIntent.GOAL_PLANNING, answer="Review the estimated reserve.", claims=[CoachClaim(claim_id="reserve", text="The estimated reserve is 123.45 BDT.", evidence_ids=[supporting.evidence_id])])
    validated, report = validate_coach_response(response, package)
    assert len(validated.claims) == 1 and report.dropped_claims_count == 0
    response.claims[0].evidence_ids = ["ev_priority_invented"]
    _, report = validate_coach_response(response, package)
    assert report.dropped_claims_count == 1


def test_existing_engine_scope_remains_the_tenant_boundary(data):
    from app.services.finance.coaching import financial_coaching
    db, users = data
    first = seed(db, users[0], target="10000.01")
    other = seed(db, users[1], target="98765.43")
    other.name = "Other tenant private goal"
    db.commit()
    outputs = []
    for user in users:
        plan = build_financial_plan(financial_coaching(db, user.id, as_of=DAY),
                                   goal_planning=planning_overview(db, user.id, schedules_confirmed=True, as_of=DAY))
        outputs.append(prioritize_financial_plan(plan))
    assert [g.goal_id for g in outputs[0].goal_planning.goals] == [first.id]
    assert [g.goal_id for g in outputs[1].goal_planning.goals] == [other.id]
    assert other.name not in outputs[0].model_dump_json()
    assert outputs[0].goal_planning.total_target_amount == D("10000.01")


def test_source_input_order_does_not_change_issue_order(goals):
    plan = build_financial_plan(coaching("cash_risk", "repeated_spending", "savings_opportunity"), goal_planning=goals, financial_health=health())
    first = prioritize_financial_plan(plan)
    plan.priorities.reverse()
    plan.actions.reverse()
    plan.evidence.reverse()
    second = prioritize_financial_plan(plan)
    assert first.model_dump_json() == second.model_dump_json()


def test_policy_evidence_matches_exact_produced_decisions():
    decisions = result("cash_risk", "upcoming_obligations", "repeated_spending", "savings_opportunity", profile=health())
    policy = next(e for e in decisions.evidence if e.evidence_id == "ev_priority_policy")
    assert policy.value["priorities"] == [p.model_dump() for p in decisions.priorities]
    assert policy.value["conflicts"] == [c.model_dump() for c in decisions.conflicts]


def test_unmatched_goal_signal_does_not_borrow_another_goals_capacity(goals):
    source = coaching("goal_risk")
    source.recommendations[0].evidence.goal_id = 999999
    decisions = prioritize_financial_plan(build_financial_plan(source, goal_planning=goals))
    unmatched = next(p for p in decisions.priorities if "goal_risk:goal_risk" in p.source_action_ids)
    assert unmatched.blocking_factors == ["goal_capacity_unknown"]


def test_per_goal_insufficient_data_remains_a_blocker(goals):
    goals.goals[0].feasibility = "insufficient_data"
    decisions = result(overview=goals)
    item = next(p for p in decisions.priorities if p.priority_id == f"priority:goal:{goals.goals[0].goal_id}")
    assert "goal_capacity_unknown" in item.blocking_factors
    assert decisions.goal_planning.capacity.status == "sufficient"
