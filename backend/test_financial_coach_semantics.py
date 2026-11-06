"""Adversarial outputs are stubs; validation never calls a provider."""
from datetime import date
from decimal import Decimal as D

import pytest

from app.schemas.financial_coach import CoachEvidence, CoachIntent, CoachResponse, CoachClaim, CoachAction, EvidenceType
from app.services.finance.financial_coach_evidence import EvidencePackage
from app.services.finance.financial_coach_validator import validate_coach_response
from app.services.finance.financial_coach_generator import FinancialCoachGenerator

DAY = date(2026, 11, 1)


def evidence(value=D("5000"), label="Recorded expenses", unit="BDT", kind=EvidenceType.DERIVED_FACT, day=DAY):
    return CoachEvidence(evidence_id="fact", evidence_type=kind, source="test", label=label,
                         value=value, unit=unit, as_of_date=day)


def package(ev):
    return EvidencePackage(intent=CoachIntent.SPENDING_ANALYSIS, as_of_date=DAY, evidence=ev)


@pytest.mark.parametrize("text,ev", [
    ("Your available cash is 5000 BDT.", evidence()),
    ("Your available cash is 999999.", evidence()),
    ("Your cash is 5000.", evidence()),
    ("Your available cash is 5000BDT.", evidence()),
    ("Your available cash is BDT5000.", evidence()),
    ("আপনার ব্যবহারযোগ্য নগদ ৫০০০টাকা।", evidence()),
    ("Your expenses are 5000 INR.", evidence()),
    ("Expenses are 5000 BDT, cash is 5000 BDT.", evidence()),
    ("Your expenses are 5000 BDT and available cash is 5000.", evidence()),
    ("Your expenses are BDT 5000 USD.", evidence(unit="USD")),
    ("Your expenses decreased by 5000 BDT.", evidence()),
    ("Your expenses are not 5000 BDT.", evidence()),
    ("Your available cash is 5000.", evidence()),
    ("Your account balance is 5000 BDT.", evidence(label="Recorded income")),
    ("Your expenses are 5000 BDT.", evidence(unit="count")),
    ("Your expenses are 5000 BDT.", evidence(unit="%")),
    ("Your expenses are 5000 BDT.", evidence(unit="months")),
    ("Your expenses are 5000 BDT.", evidence(value=D("-5000"))),
    ("Your expenses are -5000 BDT.", evidence()),
    ("Your available cash is 999999 USD.", evidence()),
    ("Your expenses are 5000 USD.", evidence()),
    ("Your expenses are 5000 BDT.", evidence(unit="USD")),
    ("Your account balance is 0 BDT.", evidence(value=None, label="Account balance")),
    ("Your savings are 5000 BDT.", evidence(label="Estimated savings", kind=EvidenceType.ESTIMATE)),
    ("Your estimated expenses are 5000 BDT.", evidence()),
    ("Your expenses today are 5000 BDT.", evidence(day=date(2026, 10, 1))),
    ("Your expenses on 2026-10-01 are 5000 BDT.", evidence()),
    ("আপনার ব্যবহারযোগ্য নগদ ৫০০০ টাকা।", evidence()),
    ("আপনার হাতে থাকা টাকা ৯৯৯৯৯৯।", evidence()),
    ("আপনার অ্যাকাউন্টের ব্যালেন্স ৫০০০ টাকা।", evidence(label="Recorded income")),
])
def test_semantic_misuse_falls_back(text, ev, monkeypatch):
    # Stub the generator at the same seam used by the API.
    monkeypatch.setattr(FinancialCoachGenerator, "generate_response", lambda *a, **kw:
                        CoachResponse(intent=CoachIntent.SPENDING_ANALYSIS, answer=text))
    p = package([ev])
    response = FinancialCoachGenerator().generate_response(p, "test")
    validated, report = validate_coach_response(response, p)
    assert not report.is_valid
    assert report.repaired
    assert validated.answer != text
    assert "999999" not in validated.answer
    assert "999,999" not in validated.answer


@pytest.mark.parametrize("text,ev", [
    ("Your recorded expenses are 0 BDT.", evidence(value=D("0"))),
    ("Your recorded expenses are -5000 BDT.", evidence(value=D("-5000"))),
    ("Your recorded income is 5000 BDT.", evidence(label="Recorded income")),
    ("Your estimated savings are 5000 BDT.", evidence(label="Estimated savings", kind=EvidenceType.ESTIMATE)),
    ("আপনার নথিভুক্ত খরচ ৫০০০ টাকা।", evidence()),
    ("Your expenses are 5000 USD.", evidence(unit="USD")),
    ("Your expenses as of 2026-10-01 were 5000 BDT.", evidence(day=date(2026, 10, 1))),
])
def test_correct_metric_value_unit_type_and_date_pass(text, ev):
    validated, report = validate_coach_response(CoachResponse(intent=CoachIntent.SPENDING_ANALYSIS, answer=text), package([ev]))
    assert report.is_valid
    assert not report.repaired
    assert validated.answer == text


@pytest.mark.parametrize("field", ["summary", "claim", "action"])
def test_all_surfaces_enforce_meaning(field):
    p = package([evidence()])
    r = CoachResponse(intent=p.intent, answer="Recorded expenses are 5000 BDT.")
    wrong = "Your available cash is 5000 BDT."
    if field == "summary": r.summary = wrong
    if field == "claim": r.claims = [CoachClaim(claim_id="bad", text=wrong, evidence_ids=["fact"])]
    if field == "action": r.actions = [CoachAction(action_id="bad", title="Review", description=wrong, evidence_ids=["fact"])]
    validated, report = validate_coach_response(r, p)
    assert report.repaired
    assert wrong not in [validated.summary, *[c.text for c in validated.claims], *[a.description for a in validated.actions]]


def test_external_ai_disabled_never_calls_provider(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", False)
    def forbidden(*args, **kwargs): raise AssertionError("external provider called")
    monkeypatch.setattr(FinancialCoachGenerator, "_call_llm", forbidden)
    p = package([evidence(value=None, label="Account balance")])
    response = FinancialCoachGenerator().generate_response(p, "What is my available cash?")
    validated, _ = validate_coach_response(response, p)
    assert "0 BDT" not in validated.answer
    assert "0.00 BDT" not in validated.answer


@pytest.fixture(autouse=True)
def forbid_external_model(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Deterministic semantic tests cannot call an external LLM")
    monkeypatch.setattr(FinancialCoachGenerator, "_call_llm", forbidden)


@pytest.mark.parametrize("text", [
    "Your emergency fund is 5000.",
    "You have 5000 to spend based on recorded expenses.",
    "Expenses give you 5000 BDT in available cash.",
    "Your expenses are 5000 XYZ.",
    "Your emergency fund is 5000 BDT.",
    "Your rainy-day fund is 5000.",
    "Your nest egg is 5000.",
    "Your magic cushion is 5000.",
    "Your purchasing power is 5000.",
    "Your wealth is 5000 BDT.",
    "You have 5000 to spend.",
    "There is 5000 set aside for emergencies.",
    "Expenses were 5000 BDT, emergency funds are 5000.",
    "Expenses were 5000, your magic bucket contains 5000.",
    "Your available cash or expenses are 5000.",
    "Total wealth is 5000 BDT.",
    "Your cash is 5000 months.",
    "Your available cash is 5000%.",
    "Your expenses are 5000.001 BDT.",
    "Your expenses are 5,00 BDT.",
    "Your expenses are -BDT5000.",
    "আপনার জরুরি তহবিল ৫০০০।",
    "আপনার জরুরি সঞ্চয় ৫০০০ টাকা।",
])
def test_unknown_or_ambiguous_money_fails_closed_without_currency(text):
    from app.services.finance.financial_coach_semantics import unsupported_financial_text
    assert unsupported_financial_text(text, [evidence()], DAY)
    validated, report = validate_coach_response(CoachResponse(intent=CoachIntent.SPENDING_ANALYSIS, answer=text), package([evidence()]))
    assert not report.is_valid
    assert validated.answer != text
    assert not unsupported_financial_text(validated.answer, package([evidence()]).evidence, DAY)


@pytest.mark.parametrize("text", [
    "You recorded 5 transactions.", "You have 3 active goals.",
    "You have 2 active financial alerts.", "You have 4 saved scenarios.",
    "Data coverage is 75%.", "Your financial health score is 50 / 100 points.",
    "Review the last 3 months.", "Review the past 30 days.",
    "Keep records for 3 to 6 months.", "Review records as of 2026-11-01.",
    "Recorded expenses are 5000 BDT across 5 transactions.",
    "আপনার রেকর্ডে ৫টি লেনদেন আছে।",
])
def test_nonmonetary_counts_dates_percentages_and_durations_remain_valid(text):
    from app.services.finance.financial_coach_semantics import unsupported_financial_text
    assert not unsupported_financial_text(text, [evidence()], DAY)


@pytest.mark.parametrize("change", [
    {"source": ""}, {"as_of_date": None}, {"value": None},
    {"label": "Available cash", "evidence_id": "ev_spending_total_expenses"},
    {"evidence_type": EvidenceType.INTERPRETATION},
])
def test_incomplete_or_conflicting_metadata_cannot_authorize_money(change):
    from app.services.finance.financial_coach_semantics import financial_facts
    assert not financial_facts([evidence().model_copy(update=change)])


def test_duplicate_ids_and_cash_inference_are_rejected():
    from app.services.finance.financial_coach_semantics import financial_facts, unsupported_financial_text
    assert not financial_facts([evidence(), evidence()])
    for label in ["Recorded expenses", "Recorded income", "Recorded savings", "Account balance"]:
        assert unsupported_financial_text("Your available cash is 5000.", [evidence(label=label)], DAY)


def test_fallback_rechecks_each_reference_and_cannot_reuse_other_evidence(monkeypatch):
    from app.services.finance.financial_coach_generator import DeterministicFallbackGenerator
    from app.services.finance.financial_coach_semantics import unsupported_financial_text
    facts = [evidence(), evidence(value=None, label="Account balance").model_copy(update={"evidence_id": "missing"})]
    def fallback(*args, **kwargs):
        return CoachResponse(intent=CoachIntent.SPENDING_ANALYSIS,
            answer="Your emergency fund is 5000.", summary="Your available cash is 0.",
            claims=[CoachClaim(claim_id="bad", text="Recorded expenses are 5000 BDT.", evidence_ids=["missing"])],
            actions=[CoachAction(action_id="bad", title="Review", description="Your emergency fund is 5000.")])
    monkeypatch.setattr(DeterministicFallbackGenerator, "generate", fallback)
    validated, _ = validate_coach_response(CoachResponse(intent=CoachIntent.SPENDING_ANALYSIS, answer="Your cash is 999999."), package(facts))
    assert not validated.claims
    assert not validated.actions
    assert validated.summary is None
    assert "999999" not in validated.answer
    assert "available cash is 0" not in validated.answer
    assert not unsupported_financial_text(validated.answer, facts, DAY)


def test_utf8_bengali_source_literals_and_digit_mapping():
    import ast
    from pathlib import Path
    from app.services.finance import financial_coach_semantics as semantics
    for filename in [Path(semantics.__file__), Path(__file__)]:
        source = filename.read_bytes().decode("utf-8", errors="strict")
        tree = ast.parse(source)
        assert "\ufffd" not in source
        assert "\u00e0\u00a6" not in source
        assert "\u00e0\u00a7" not in source
        if filename.name == "financial_coach_semantics.py":
            call = next(node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "DIGITS" for target in node.targets))
            src, dst = [ast.literal_eval(arg) for arg in call.args]
            assert len(src) == len(dst) == 10
            assert [ord(ch) for ch in src] == list(range(0x09E6, 0x09F0))
            assert dst == "0123456789"
            assert src.translate(semantics.DIGITS) == dst
    assert semantics.CURRENCY.search("টাকা")
    assert semantics.metric("জরুরি তহবিল") == "emergency_fund"


@pytest.mark.parametrize("kind,text,expected", [
    (EvidenceType.RAW_DATA, "Recorded expenses are 5000 BDT.", False),
    (EvidenceType.RAW_DATA, "Derived expenses are 5000 BDT.", True),
    (EvidenceType.DERIVED_FACT, "Derived expenses are 5000 BDT.", False),
    (EvidenceType.ESTIMATE, "Recorded estimated expenses are 5000 BDT.", True),
    (EvidenceType.ESTIMATE, "Estimated expenses are 5000 BDT.", False),
])
def test_recorded_derived_estimated_classification(kind, text, expected):
    from app.services.finance.financial_coach_semantics import unsupported_financial_text
    assert unsupported_financial_text(text, [evidence(kind=kind)], DAY) is expected
