from datetime import date

from app.schemas.financial_coach import CoachEvidence, EvidenceType
from app.schemas.financial_plan import FinancialDecisionSet, FinancialPriority
from app.schemas.intelligence import IntelligencePeriod
from app.services.finance.financial_execution import build_financial_execution_plan


def test_execution_preserves_source_evidence_and_no_amounts():
    day = date(2026, 10, 31)
    period = IntelligencePeriod(kind="month", start=day, end=date(2026, 11, 30), is_complete=False, label="October 2026")
    evidence = CoachEvidence(evidence_id="ev1", evidence_type=EvidenceType.DERIVED_FACT, source="cashflow", label="Cashflow", value="risk", as_of_date=day)
    priority = FinancialPriority(priority_id="p1", category="cashflow_risk", level="high", title="Cashflow", reason="cashflow_constraint", evidence_ids=["ev1"], evidence_quality="derived")
    decisions = FinancialDecisionSet(as_of_date=day, planning_horizon=period, data_status="sufficient", priorities=[priority], evidence=[evidence])
    result = build_financial_execution_plan(decisions)
    assert result.steps[0].evidence_ids == ["ev1"]
    assert result.steps[0].requires_user_confirmation is True
    assert "amount" not in result.steps[0].model_fields
