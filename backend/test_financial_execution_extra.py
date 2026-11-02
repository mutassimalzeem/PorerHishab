from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import socket

import pytest

from app.schemas.financial_execution import FinancialActionStep, FinancialExecutionPlan
from app.schemas.financial_coach import CoachEvidence, EvidenceType
from app.schemas.financial_plan import FinancialDecisionSet, FinancialPriority
from app.schemas.intelligence import IntelligencePeriod
from app.services.finance.financial_execution import build_financial_execution_plan
from test_financial_execution import decision_set, priority
from test_goal_planning import data  # noqa: F401


def test_execution_preserves_source_evidence_and_no_amounts():
    day = date(2026, 10, 31)
    period = IntelligencePeriod(kind="month", start=day, end=date(2026, 11, 30), is_complete=False, label="October 2026")
    evidence = CoachEvidence(evidence_id="ev1", evidence_type=EvidenceType.DERIVED_FACT, source="cashflow", label="Cashflow", value="risk", as_of_date=day)
    priority = FinancialPriority(priority_id="p1", category="cashflow_risk", level="high", title="Cashflow", reason="cashflow_constraint", evidence_ids=["ev1"], evidence_quality="derived")
    decisions = FinancialDecisionSet(as_of_date=day, planning_horizon=period, data_status="sufficient", priorities=[priority], evidence=[evidence])
    result = build_financial_execution_plan(decisions)
    assert result.steps[0].evidence_ids == ["ev1"]
    assert result.steps[0].requires_user_confirmation is True
    assert "amount" not in FinancialActionStep.model_fields
    assert "amount" not in result.steps[0].model_dump()


# Safety regressions use valid upstream contracts before attempting output tampering.


@pytest.mark.parametrize("field,value,match", [
    ("state", "ready", "unresolved blockers"),
    ("requires_user_confirmation", False, "requires_user_confirmation"),
    ("amount", "100.00", "Extra inputs"),
])
def test_step_cannot_bypass_blockers_confirmation_or_add_money(field, value, match):
    decisions = decision_set([priority("p1", "goal_review", factors=["goal_capacity_unknown"])])
    payload = build_financial_execution_plan(decisions).steps[0].model_dump()
    payload[field] = value
    with pytest.raises(ValueError, match=match):
        FinancialActionStep.model_validate(payload)


def test_parent_contract_revalidates_mutated_step_instances():
    plan = build_financial_execution_plan(decision_set([priority("p1", "goal_review", factors=["goal_capacity_unknown"])]))
    plan.steps[0].state = "ready"
    with pytest.raises(ValueError, match="unresolved blockers"):
        FinancialExecutionPlan(**{**plan.model_dump(), "steps": plan.steps})


@pytest.mark.parametrize("corruption", ["unknown_evidence", "reversed_dependencies", "wrong_evidence_date", "duplicate_priority"])
def test_service_reuses_upstream_validation(corruption):
    decisions = decision_set([priority("p1", "cashflow_risk"), priority("p2", "savings_opportunity", blocking=["p1"])])
    if corruption == "unknown_evidence":
        decisions.priorities[0].evidence_ids = ["absent"]
    elif corruption == "reversed_dependencies":
        decisions.priorities.reverse()
    elif corruption == "wrong_evidence_date":
        decisions.evidence[0].as_of_date -= timedelta(days=1)
    else:
        decisions.priorities.append(decisions.priorities[0])
    with pytest.raises(ValueError):
        build_financial_execution_plan(decisions)


def test_duplicate_priorities_cannot_make_ambiguous_step_dependencies():
    plan = build_financial_execution_plan(decision_set([priority("p1", "cashflow_risk")])).model_dump()
    duplicate = deepcopy(plan["steps"][0])
    duplicate.update(step_id="different-step", sequence=2)
    plan["steps"].append(duplicate)
    with pytest.raises(ValueError, match="Duplicate execution priority IDs"):
        FinancialExecutionPlan.model_validate(plan)


def test_execution_is_deterministic_detached_and_has_no_io(monkeypatch):
    from sqlalchemy.orm import Session
    from app.services.finance.financial_coach_generator import FinancialCoachGenerator
    decisions = decision_set([priority("p1", "cashflow_risk"), priority("p2", "savings_opportunity", blocking=["p1"])])
    decisions.data_status = "insufficient_data"
    decisions.evidence[0].value = {"observed_amount": Decimal("123.45")}
    before = deepcopy(decisions.model_dump())
    def forbidden(*args, **kwargs):
        pytest.fail("Execution planning attempted I/O or generation")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(Session, "query", forbidden)
    monkeypatch.setattr(Session, "execute", forbidden)
    monkeypatch.setattr(FinancialCoachGenerator, "generate_response", forbidden)
    first = build_financial_execution_plan(decisions)
    second = build_financial_execution_plan(decisions)
    assert first.model_dump_json() == second.model_dump_json()
    assert first.data_status == "insufficient_data"
    first.planning_horizon.label = "Changed"
    first.evidence[0].value["observed_amount"] = "Changed"
    first.steps[0].limitations.append("Changed")
    assert decisions.model_dump() == before


def test_real_planning_chain_preserves_goals_and_evidence(data):
    from test_goal_planning import seed, DAY
    from app.services.finance.coaching import financial_coaching
    from app.services.finance.goal_planning import planning_overview
    from app.services.finance.financial_planner import build_financial_plan
    from app.services.finance.financial_prioritization import prioritize_financial_plan
    db, users = data
    seed(db, users[0], target="10000.01")
    overview = planning_overview(db, users[0].id, schedules_confirmed=True, as_of=DAY)
    decisions = prioritize_financial_plan(build_financial_plan(financial_coaching(db, users[0].id, as_of=DAY), goal_planning=overview))
    before = decisions.model_dump()
    result = build_financial_execution_plan(decisions)
    assert [s.priority_id for s in result.steps] == [p.priority_id for p in decisions.priorities]
    assert result.evidence == decisions.evidence
    assert decisions.model_dump() == before
    assert decisions.goal_planning == overview



@pytest.mark.parametrize("corruption", ["unknown_reference", "duplicate_evidence", "duplicate_blocker", "wrong_date", "reversed_steps"])
def test_execution_contract_rejects_invalid_provenance_or_dependencies(corruption):
    decisions = decision_set([priority("p1", "cashflow_risk"), priority("p2", "savings_opportunity", blocking=["p1"])])
    payload = build_financial_execution_plan(decisions).model_dump()
    if corruption == "unknown_reference":
        payload["steps"][0]["evidence_ids"] = ["absent"]
    elif corruption == "duplicate_evidence":
        payload["evidence"].append(deepcopy(payload["evidence"][0]))
    elif corruption == "duplicate_blocker":
        payload["steps"][1]["blocking_priority_ids"] = ["p1", "p1"]
    elif corruption == "wrong_date":
        payload["evidence"][0]["as_of_date"] -= timedelta(days=1)
    else:
        payload["steps"].reverse()
        for sequence, step in enumerate(payload["steps"], 1):
            step["sequence"] = sequence
    with pytest.raises(ValueError):
        FinancialExecutionPlan.model_validate(payload)
