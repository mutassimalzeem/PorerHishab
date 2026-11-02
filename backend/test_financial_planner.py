"""Offline AI-16A composition, provenance and authoritative-engine regressions."""
from datetime import date, timedelta
from decimal import Decimal as D
from copy import deepcopy
import socket

import pytest
from pydantic import ValidationError

from app.schemas.coaching import FinancialCoaching
from app.schemas.financial_coach import CoachClaim, CoachIntent, CoachResponse, EvidenceType
from app.schemas.financial_health import FinancialHealthComponent, FinancialHealthEvidence, FinancialHealthProfile
from app.schemas.financial_plan import FinancialPlan
from app.schemas.goal_planning import GoalPlanningOverview
from app.services.finance.coaching import recommendation, financial_coaching
from app.services.finance.financial_planner import build_financial_plan, plan_evidence_package
from app.services.finance.financial_coach_validator import validate_coach_response
from app.services.finance.goal_planning import planning_overview
from app.services.finance.financial_health import gather_profile
from test_goal_planning import data, seed, DAY  # noqa: F401


def coaching(*kinds, status="sufficient"):
    period = dict(kind="coaching_horizon", start=DAY, end=DAY + timedelta(days=30), is_complete=False, label="30 days")
    priorities = {"cash_risk": "critical", "upcoming_obligations": "high", "goal_risk": "medium", "repeated_spending": "medium", "savings_opportunity": "low"}
    sources = {"cash_risk": "financial_runway", "upcoming_obligations": "scheduled_cashflow", "goal_risk": "goal_assessment", "repeated_spending": "category_spending", "savings_opportunity": "financial_runway"}
    recs = [recommendation(kind, kind, DAY, period["end"], priority=priorities[kind], source=sources[kind],
                           evidence=dict(period=period, observed_value=D("123.45")),
                           amount=D("123.45") if kind == "savings_opportunity" else None,
                           limitations=["Source limitation"]) for kind in kinds]
    return FinancialCoaching(as_of_date=DAY, period=period, data_status=status, recommendations=recs, limitations=[])


def health(status="strained", *, available=True):
    from datetime import datetime, timezone
    comp = FinancialHealthComponent(key="liquidity", score=D("20") if available else None,
                                    status=status, data_available=available, explanation="Existing liquidity assessment",
                                    evidence=[FinancialHealthEvidence(metric="trusted_cash", value=D("100.01"), unit="BDT", source="account_position", as_of_date=DAY, observed_at=datetime(2026, 11, 1, tzinfo=timezone.utc))])
    return FinancialHealthProfile(as_of_date=DAY, components=[comp], status=status,
                                  available_components=["liquidity"] if available else [],
                                  missing_components=[] if available else ["liquidity"])


def test_healthy_no_invented_goals_or_actions():
    plan = build_financial_plan(coaching(), financial_health=health("strong"))
    assert plan.actions == plan.priorities == plan.evidence == []
    assert plan.goal_planning is None and plan.data_status == "partial"
    assert any("unknown" in x for x in plan.limitations)


def test_competing_priorities_and_source_amount_semantics():
    source = coaching("savings_opportunity", "repeated_spending", "goal_risk", "cash_risk", "upcoming_obligations")
    plan = build_financial_plan(source, financial_health=health())
    assert [p.action_id for p in plan.priorities] == [
        "cash_risk:cash_risk", "upcoming_obligations:upcoming_obligations", "plan:emergency_reserve",
        "goal_risk:goal_risk", "repeated_spending:repeated_spending", "savings_opportunity:savings_opportunity"]
    assert plan.actions[-1].amount == D("123.45")
    assert "monthly" not in type(plan.actions[-1]).model_fields
    assert all(p.evidence_ids for p in plan.priorities)
    assert {e.evidence_type for e in plan.evidence} == {EvidenceType.ESTIMATE, EvidenceType.INTERPRETATION}


@pytest.mark.parametrize("status", ["watch", "strained", "stable", "strong", "insufficient_data"])
def test_reserve_review_uses_only_available_existing_health(status):
    plan = build_financial_plan(coaching(), financial_health=health(status, available=status != "insufficient_data"))
    assert bool(plan.priorities) == (status in {"watch", "strained"})
    assert plan.actions == []  # No new allocation is fabricated.


def test_insufficient_data_never_substitutes_zero():
    plan = build_financial_plan(coaching(status="insufficient_data"))
    assert plan.data_status == "insufficient_data"
    assert plan.goal_planning is None and plan.financial_health is None
    assert plan.actions == plan.priorities == []
    assert plan_evidence_package(plan).missing_data


def test_stale_recommendations_are_excluded():
    source = coaching("cash_risk", "savings_opportunity")
    source.recommendations[0].valid_until = DAY - timedelta(days=1)
    source.recommendations[1].as_of_date = DAY + timedelta(days=1)
    plan = build_financial_plan(source)
    assert not plan.priorities and not plan.actions
    assert plan.warnings[0].code == "STALE_RECOMMENDATIONS"


@pytest.mark.parametrize("days", [-1, 367])
def test_invalid_horizon(days):
    source = coaching()
    source.period.end = DAY + timedelta(days=days)
    with pytest.raises(ValueError, match="horizon"):
        build_financial_plan(source)


def test_same_day_horizon_and_cross_date_rejection():
    source = coaching()
    source.period.end = DAY
    assert build_financial_plan(source).planning_horizon.end == DAY
    old_health = health()
    old_health.as_of_date -= timedelta(days=1)
    with pytest.raises(ValueError, match="date"):
        build_financial_plan(source, financial_health=old_health)
    source.period.start -= timedelta(days=1)
    with pytest.raises(ValueError, match="horizon"):
        build_financial_plan(source)


def test_determinism_no_network_and_no_mutation(monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("Planner attempted network access"))
    source = coaching("cash_risk", "savings_opportunity")
    profile = health()
    before = deepcopy((source.model_dump(), profile.model_dump()))
    one = build_financial_plan(source, financial_health=profile)
    two = build_financial_plan(source, financial_health=profile)
    assert one.model_dump_json() == two.model_dump_json()
    assert before == (source.model_dump(), profile.model_dump())
    one.evidence[0].value["evidence"]["observed_value"] = D("999")
    one.actions[0].limitations.append("Changed")
    assert before == (source.model_dump(), profile.model_dump())
    package = plan_evidence_package(two)
    package.evidence[0].value["amount"] = D("999")
    assert package.evidence[0].value != two.evidence[0].value


def test_contract_rejects_ungrounded_decisions_and_duplicate_ids():
    plan = build_financial_plan(coaching("cash_risk"))
    payload = plan.model_dump()
    payload["priorities"][0]["evidence_ids"] = ["fabricated"]
    with pytest.raises(ValidationError, match="existing evidence"):
        FinancialPlan.model_validate(payload)
    source = coaching("cash_risk", "cash_risk")
    with pytest.raises(ValueError, match="Duplicate recommendation"):
        build_financial_plan(source)


def test_existing_critical_action_limit_is_preserved():
    source = coaching("cash_risk")
    rec = source.recommendations[0]
    source.recommendations = [rec.model_copy(update={"id": f"risk:{i}"}) for i in range(7)]
    plan = build_financial_plan(source)
    assert len(plan.actions) == len(plan.priorities) == 7


def test_recorded_derived_evidence_classification():
    source = coaching("repeated_spending")
    source.recommendations[0].evidence_quality = "recorded"
    plan = build_financial_plan(source)
    assert plan.evidence[0].evidence_type == EvidenceType.DERIVED_FACT


def test_coach_validation_accepts_produced_evidence_rejects_invented_provenance():
    plan = build_financial_plan(coaching("savings_opportunity"))
    package = plan_evidence_package(plan)
    response = CoachResponse(intent=CoachIntent.GOAL_PLANNING, answer="Review the estimated savings opportunity.",
                             claims=[CoachClaim(claim_id="supported", text="The estimated reserve is 123.45 BDT.", evidence_ids=[plan.evidence[0].evidence_id])],
                             actions=plan.priorities)
    validated, report = validate_coach_response(response, package)
    assert len(validated.claims) == len(validated.actions) == 1
    assert report.dropped_claims_count == report.dropped_actions_count == 0
    response.claims[0].evidence_ids = ["ev_plan_invented"]
    validated, report = validate_coach_response(response, package)
    assert report.dropped_claims_count == 1
    assert all(c.claim_id != "supported" for c in validated.claims)


def test_real_engines_shared_pool_dates_and_decimal_roundtrip(data):
    db, users = data
    seed(db, users[0], target="10000.01", priority=1)
    seed(db, users[0], target="20000.02", priority=5)
    overview = planning_overview(db, users[0].id, schedules_confirmed=True, as_of=DAY)
    profile = gather_profile(db, users[0].id, as_of=DAY)
    source = financial_coaching(db, users[0].id, as_of=DAY)
    before = overview.model_dump()
    plan = build_financial_plan(source, goal_planning=overview, financial_health=profile)
    assert plan.goal_planning.model_dump() == before
    assert sum((g.proposed_monthly for g in plan.goal_planning.goals), D(0)) <= overview.capacity.conservative_monthly_capacity
    assert plan.goal_planning.total_target_amount == D("30000.03")
    restored = FinancialPlan.model_validate_json(plan.model_dump_json())
    assert restored.model_dump_json() == plan.model_dump_json()
    assert restored.goal_planning.goals[0].target_amount == D("10000.01")
    plan.goal_planning.goals[0].proposed_monthly = D("0")
    assert overview.model_dump() == before
    other = build_financial_plan(financial_coaching(db, users[1].id, as_of=DAY),
                                 goal_planning=planning_overview(db, users[1].id, as_of=DAY))
    assert other.goal_planning.goals == [] and other.actions == []


@pytest.mark.parametrize("condition", ["zero_income", "zero_expenses", "zero_cash", "negative_cashflow", "missing_savings", "impossible_goal", "same_day", "no_deadline", "large"])
def test_engine_edge_conditions_are_preserved(data, condition):
    from app.models import Transaction
    db, users = data
    target = "99999999999.99" if condition in {"large", "impossible_goal"} else "10000.01"
    goal = seed(db, users[0], target=target, saved=None if condition == "missing_savings" else "0", cash="0" if condition == "zero_cash" else "100000", deadline=DAY if condition == "same_day" else date(2027, 4, 30))
    if condition in {"zero_income", "zero_expenses", "negative_cashflow"}:
        for row in db.query(Transaction).filter_by(user_id=users[0].id):
            if row.amount > 0 and condition == "zero_income":
                row.amount = D("0")
            elif row.amount < 0:
                row.amount = D("0") if condition == "zero_expenses" else D("-50000") if condition == "negative_cashflow" else row.amount
    if condition == "no_deadline":
        goal.target_date = None
    db.commit()
    overview = planning_overview(db, users[0].id, schedules_confirmed=True, as_of=DAY)
    plan = build_financial_plan(financial_coaching(db, users[0].id, as_of=DAY), goal_planning=overview,
                                financial_health=gather_profile(db, users[0].id, as_of=DAY))
    assert plan.goal_planning == overview
    if condition in {"zero_income", "zero_expenses", "missing_savings"}:
        assert plan.goal_planning.capacity.conservative_monthly_capacity is None
        assert any(w.code == "UNKNOWN_PLANNING_CAPACITY" for w in plan.warnings)
    if condition == "negative_cashflow":
        assert plan.priorities[0].action_id == "plan:negative_cashflow"
    assert plan.planner_version == "ai-16a-v1"


def test_cross_date_goal_and_duplicate_goal_health_rejection(data):
    db, users = data
    seed(db, users[0])
    overview = planning_overview(db, users[0].id, schedules_confirmed=True, as_of=DAY)
    overview.capacity.as_of_date -= timedelta(days=1)
    with pytest.raises(ValueError, match="date"):
        build_financial_plan(coaching(), goal_planning=overview)
    overview.capacity.as_of_date = DAY
    overview.goals.append(overview.goals[0])
    with pytest.raises(ValueError, match="Duplicate goal"):
        build_financial_plan(coaching(), goal_planning=overview)
    profile = health()
    profile.components.append(profile.components[0])
    with pytest.raises(ValueError, match="Duplicate health"):
        build_financial_plan(coaching(), financial_health=profile)


def test_over_capacity_and_conflicting_health_do_not_override_cash_risk(data):
    db, users = data
    seed(db, users[0])
    overview = planning_overview(db, users[0].id, schedules_confirmed=True, as_of=DAY)
    overview.over_capacity = True
    plan = build_financial_plan(coaching("cash_risk"), goal_planning=overview, financial_health=health("strong"))
    assert plan.priorities[0].action_id.startswith("cash_risk:")
    assert {w.code for w in plan.warnings} == {"GOAL_OVER_CAPACITY", "CASH_RISK_BEFORE_GOALS"}
    assert plan.goal_planning == overview
    assert all(p.action_id != "plan:emergency_reserve" for p in plan.priorities)


@pytest.mark.parametrize("margin,expected", [("-0.25", True), (-1, True), ("0", False), ("0.25", False), ("unknown", False), ("NaN", False), ("-Infinity", False)])
def test_existing_margin_evidence_after_json_restoration(margin, expected):
    profile = health("strong")
    component = profile.components[0]
    component.key = "cashflow_stability"
    component.evidence[0].metric = "mean_surplus_margin"
    component.evidence[0].value = margin
    profile = FinancialHealthProfile.model_validate_json(profile.model_dump_json())
    plan = build_financial_plan(coaching(), financial_health=profile)
    assert any(p.action_id == "plan:negative_cashflow" for p in plan.priorities) == expected


def test_existing_goal_milestones_are_preserved(data):
    from app.services.finance.goal_planning import create_plan
    from app.schemas.goal_planning import PlanRequest
    db, users = data
    goal = seed(db, users[0], target="10000.01")
    create_plan(db, users[0].id, goal.id, PlanRequest(idempotency_key="ai16a-milestone-test", schedules_confirmed=True), as_of=DAY)
    overview = planning_overview(db, users[0].id, schedules_confirmed=True, as_of=DAY)
    assert overview.upcoming_milestones
    plan = build_financial_plan(financial_coaching(db, users[0].id, as_of=DAY), goal_planning=overview)
    assert plan.goal_planning.upcoming_milestones == overview.upcoming_milestones
    assert plan.goal_planning.upcoming_milestones[-1].due_date == goal.target_date
