"""Evaluation runner for transaction categorization (AI-12C).

Execution flow per case:
    labeled case -> categorize_transaction (offline pipeline) -> result
    -> per-dimension scores (category, method, ambiguity) -> CaseResult
    -> CategorizationOutcome -> CategorizationReport.

Offline by construction: the default run evaluates the deterministic
pipeline with ``allow_llm=False`` — no provider is reachable.  Provider
passes are exercised in tests by injecting offline stubs into
``app.services.categorization.service.categorize_with_llm``; pathway rates
then read the ``llm``/``fallback`` execution path straight off the observed
result method, never inferred from the final category.

Case scoring (``expected_behavior`` contract):

    rule_classify      rules must confidently produce the expected category
    provider_required  safe uncertainty (fallback / provider path), never a
                       confident rule-engine guess
    never_classify     blank input must end Uncategorized via the fallback
    user_correction    the confirmed correction must win
    custom_category    user-defined label preserved verbatim
"""
from datetime import date

from app.evaluation.datasets.categorization_cases import (
    ALLOWED_BEHAVIORS,
    EVALUATION_CASES,
)
from app.evaluation.metrics import CaseResult
from app.evaluation.categorization_metrics import (
    CONFIDENT_METHODS,
    CategorizationOutcome,
    CategorizationReport,
    FALLBACK_PATH,
    LLM_PATH,
    RULE_PATH,
    summarize_categorization,
)
from app.services.categorization import service as categorization_service
from app.services.categorization.categories import ALLOWED_CATEGORIES, UNCATEGORIZED

#: Scoring dimensions for categorization; None means "does not apply".
CATEGORIZATION_SCORE_DIMENSIONS = ("category", "method", "ambiguity")

_RULE_CLASSIFY = "rule_classify"
_PROVIDER_REQUIRED = "provider_required"
_NEVER_CLASSIFY = "never_classify"
_USER_CORRECTION = "user_correction"
_CUSTOM_CATEGORY = "custom_category"


def validate_dataset(cases=None) -> list[str]:
    """Structural + labeling-rule sanity checks; returns a problem list."""
    problems: list[str] = []
    cases = cases if cases is not None else EVALUATION_CASES
    seen_ids: set[str] = set()
    corrected_merchants: set[str] = set()

    for case in cases:
        case_id = case.get("id")
        if not case_id:
            problems.append("case without an id")
            continue
        if case_id in seen_ids:
            problems.append(f"{case_id}: duplicate id")
        seen_ids.add(case_id)

        behavior = case.get("expected_behavior")
        if behavior not in ALLOWED_BEHAVIORS:
            problems.append(f"{case_id}: unknown expected_behavior {behavior!r}")
            continue

        blank = not (
            str(case.get("merchant") or "").strip()
            or str(case.get("description") or "").strip()
        )
        if blank and behavior != _NEVER_CLASSIFY:
            problems.append(f"{case_id}: blank input must expect never_classify")

        if behavior == _RULE_CLASSIFY:
            expected = case.get("expected_category")
            if not expected:
                problems.append(f"{case_id}: rule_classify needs expected_category")
            elif expected not in ALLOWED_CATEGORIES:
                problems.append(f"{case_id}: expected_category not in the taxonomy")
            if case.get("is_ambiguous"):
                problems.append(f"{case_id}: rule_classify cannot be ambiguous")
        elif behavior == _PROVIDER_REQUIRED:
            if case.get("expected_category") is not None:
                problems.append(
                    f"{case_id}: provider_required must not carry a confident label")
            if not case.get("is_ambiguous"):
                problems.append(f"{case_id}: provider_required misses is_ambiguous=True")
        elif behavior == _NEVER_CLASSIFY:
            if not blank:
                problems.append(f"{case_id}: never_classify requires blank input")

        context = case.get("user_context") or {}
        correction = context.get("confirmed_correction")
        if behavior in (_USER_CORRECTION, _CUSTOM_CATEGORY):
            if not correction or not correction.get("merchant") \
                    or not correction.get("category"):
                problems.append(f"{case_id}: correction needs merchant + category")
            else:
                normalized = correction["merchant"].strip().lower()
                if normalized in corrected_merchants:
                    problems.append(
                        f"{case_id}: corrected merchant already corrected by "
                        "another case; a preference would bleed across cases")
                corrected_merchants.add(normalized)
                if behavior == _CUSTOM_CATEGORY:
                    if correction["category"] in ALLOWED_CATEGORIES:
                        problems.append(
                            f"{case_id}: custom_category label is inside the "
                            "system taxonomy")
        elif correction:
            problems.append(
                f"{case_id}: only correction behaviors may carry user_context")

    return problems


def run_case(db, case: dict, user_id: int | None, *, allow_llm: bool = False) -> tuple[CaseResult, CategorizationOutcome]:
    """Execute one labeled case; returns (scored result, outcome trace)."""
    behavior = case["expected_behavior"]
    try:
        result = categorization_service.categorize_transaction(
            {
                "merchant": case.get("merchant"),
                "description": case.get("description"),
                "amount": (case.get("user_context") or {}).get("amount"),
            },
            db=db,
            user_id=user_id,
            allow_llm=allow_llm,
        )
        observed = result.model_dump()
        observed_status = result_observability(observed)
    except Exception as exc:  # a crash is an evaluation event, not a test error
        observed = {"category": None, "method": "error", "confidence": 0.0}
        observed_status = f"error: {type(exc).__name__}: {exc}"

    scores: dict[str, float | None] = {
        dimension: None for dimension in CATEGORIZATION_SCORE_DIMENSIONS}
    failures: list[str] = []
    category = observed.get("category")
    method = observed.get("method")
    corrected = ((case.get("user_context") or {}).get("confirmed_correction") or {}).get("category")

    def mark(dimension: str, ok: bool, message: str):
        if ok:
            scores[dimension] = 1.0 if scores[dimension] is None else scores[dimension]
        else:
            scores[dimension] = 0.0
            failures.append(message)

    if behavior == _RULE_CLASSIFY:
        expected_category = case["expected_category"]
        mark("category", category == expected_category,
             f"category: expected {expected_category!r}, observed {category!r}")
        mark("method", method == RULE_PATH,
             f"method: expected a rule-engine hit, observed {method!r}")
    elif behavior == _PROVIDER_REQUIRED:
        # Safe uncertainty: own up to not knowing instead of guessing. An
        # unresolved pipeline must end Uncategorized; a provider result is
        # accepted as resolved; anything else (crash, None) is a failure.
        mark("category", category == UNCATEGORIZED or method == LLM_PATH,
             f"category: uncertain input must stay {UNCATEGORIZED!r} (offline), "
             f"observed {category!r}")
        mark("method", method in CONFIDENT_METHODS | {FALLBACK_PATH} and method != RULE_PATH,
             f"method: expected fallback or provider path, observed {method!r}")
        if case.get("is_ambiguous"):
            mark("ambiguity", method != RULE_PATH,
                 "ambiguity: rules confidently guessed on an uncertain input")
    elif behavior == _NEVER_CLASSIFY:
        mark("category", category == UNCATEGORIZED,
             f"category: blank input must end Uncategorized, observed {category!r}")
        mark("method", method == FALLBACK_PATH,
             f"method: blank input must use the fallback path, observed {method!r}")
    elif behavior in (_USER_CORRECTION, _CUSTOM_CATEGORY):
        mark("category", category == corrected,
             f"category: confirmed correction {corrected!r} must win, observed {category!r}")
        mark("method", method == "user_preference",
             f"method: expected user_preference precedence, observed {method!r}")

    outcome = CategorizationOutcome(
        case_id=case["id"],
        group=case["group"],
        behavior=behavior,
        is_ambiguous=bool(case.get("is_ambiguous")),
        is_mixed_language=bool(case.get("is_mixed_language")),
        eligible=bool(str(case.get("merchant") or "").strip()
                      or str(case.get("description") or "").strip()),
        expected_category=case.get("expected_category"),
        observed_category=category,
        observed_method=method or "error",
        corrected_category=corrected,
    )
    case_result = CaseResult(
        case_id=case["id"],
        group=case["group"],
        expected_status=behavior,
        observed_status=observed_status,
        scores=scores,
        failures=failures,
    )
    return case_result, outcome


def result_observability(observed: dict) -> str:
    """Human-readable status for the report: method + final category."""
    return f"{observed.get('method')}:{observed.get('category')}"


def run_dataset(
    db,
    *,
    cases=None,
    allow_llm: bool = False,
    mode: str | None = None,
) -> CategorizationReport:
    """Run the categorization dataset in one isolated, correction-seeded pass."""
    cases = cases if cases is not None else EVALUATION_CASES
    mode = mode or ("provider_stub" if allow_llm else "rules_only")

    from app.models import User
    from app.models.merchant_preference import MerchantCategoryPreference
    from app.core.database import Base

    Base.metadata.create_all(bind=db.bind)

    user = User(
        email="categorization-eval@porer-hishab.local",
        hashed_password="evaluation-only",
        full_name="Categorization Evaluation",
    )
    db.add(user)
    db.commit()

    preferences: list[MerchantCategoryPreference] = []
    try:
        for case in cases:
            correction = (case.get("user_context") or {}).get("confirmed_correction")
            if correction:
                preferences.append(MerchantCategoryPreference(
                    user_id=user.id,
                    normalized_merchant=correction["merchant"].strip().lower(),
                    category=correction["category"],
                ))
        if preferences:
            db.add_all(preferences)
            db.commit()

        results, outcomes = [], []
        for case in cases:
            case_result, outcome = run_case(db, case, user.id, allow_llm=allow_llm)
            results.append(case_result)
            outcomes.append(outcome)
    finally:
        for preference in preferences:
            db.delete(preference)
        db.delete(user)
        db.commit()

    metrics = summarize_categorization(outcomes, results, mode)
    return CategorizationReport(as_of=date.today(), case_count=len(results),
                                results=results, metrics=metrics,
                                mode=mode, outcomes=outcomes)
