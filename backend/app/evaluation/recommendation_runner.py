"""AI-12D runner: savings recommendations against structured ground truth.

Two surfaces, one protocol:

* plan cases run ``calculate_savings_plan`` with a fixed ``today`` and score
  the response on grounding (pinned fields), arithmetic
  (``observed spending x reduction fraction ~= suggested cut`` within the
  configured tolerance), estimate labeling, no double counting,
  personalization, and data-sufficiency behaviour;
* coach cases run ``finance.coach.recommendations`` over a controlled
  three-month history and score the same properties, with each
  ``estimated_monthly_saving`` recomputed from the blueprint.

No provider call is involved and no wording is ever compared.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from app.evaluation.datasets.recommendation_cases import (
    ARITHMETIC_TOLERANCE,
    CANARY_SCENARIO,
    COACH_CASES,
    PLAN_CASES,
    CoachCase,
    PlanCase,
    RECOMMENDATION_AS_OF,
    RECOMMENDATION_ISOLATION_MARKERS,
    category_monthly_averages,
    clear_recommendation_scenarios,
    expected_coach_recommendations,
    expected_plan,
    seed_recommendation_scenarios,
    validate_recommendation_dataset,
)
from app.evaluation.metrics import CaseResult

#: Months the coach contract needs before making recommendations.
ADEQUATE_HISTORY_MONTHS = 3

RECOMMENDATION_SCORE_DIMENSIONS = ("grounding", "arithmetic", "estimate_labeling",
                                   "no_double_counting", "personalization",
                                   "data_sufficiency", "isolation")

PLAN_REDUCTION_FRACTION = Decimal("0.20")
COACH_REDUCTION_FRACTION = Decimal("0.10")


def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _within(observed, expected, tolerance=ARITHMETIC_TOLERANCE) -> bool:
    observed, expected = _decimal(observed), _decimal(expected)
    if observed is None or expected is None:
        return False
    return abs(observed - expected) <= tolerance


def _new_case_state(case, source):
    scores = {dimension: None for dimension in RECOMMENDATION_SCORE_DIMENSIONS}
    return {
        "case": case, "source": source,
        "scores": scores, "failures": [],
        "oks": {dimension: [] for dimension in RECOMMENDATION_SCORE_DIMENSIONS},
        "isolation": True,
    }


def _mark(state, dimension: str, ok: bool, message: str, applies: bool = True):
    if not applies:
        return
    state["oks"][dimension].append(ok)
    if ok:
        scores = state["scores"]
        scores[dimension] = 1.0 if scores[dimension] is None else scores[dimension]
    else:
        state["scores"][dimension] = 0.0
        state["failures"].append(message)


def _case_result(state, observed_status: str) -> CaseResult:
    case = state["case"]
    expected_status = getattr(case, "expected_status", "answered")
    return CaseResult(case_id=case.case_id, group=case.group,
                      expected_status=expected_status,
                      observed_status=observed_status,
                      scores=state["scores"], failures=state["failures"])


def _outcome(state):
    from app.evaluation.recommendation_metrics import RecommendationOutcome

    def verdict(dimension: str, default: bool = True) -> bool:
        marks = state["oks"][dimension]
        return all(marks) if marks else default

    return RecommendationOutcome(
        case_id=state["case"].case_id,
        group=state["case"].group,
        source=state["source"],
        grounding_checks=len(state["oks"]["grounding"]),
        grounding_passed=sum(state["oks"]["grounding"]),
        arithmetic_checks=len(state["oks"]["arithmetic"]),
        arithmetic_passed=sum(state["oks"]["arithmetic"]),
        labeling_ok=verdict("estimate_labeling"),
        double_counting_ok=verdict("no_double_counting"),
        personalization_ok=verdict("personalization"),
        data_sufficiency_ok=verdict("data_sufficiency"),
        isolation_ok=state["isolation"],
    )


def run_plan_case_with_outcome(db, case: PlanCase):
    """Evaluate one deterministic savings-plan case against the blueprint."""
    from app.repositories.transaction_repository import list_transactions_in_range
    from app.services.planning.savings import calculate_savings_plan

    state = _new_case_state(case, "plan")
    seeded = seed_recommendation_scenarios(db, (case.scenario, CANARY_SCENARIO))
    observed_status = "error"
    try:
        user = seeded[0]
        try:
            transactions = list_transactions_in_range(db, user.id)
            plan = calculate_savings_plan(
                transactions=transactions,
                goal_amount=Decimal(case.goal_amount),
                current_saved=Decimal(case.current_saved),
                target_date=date.fromisoformat(case.target_date),
                today=date.fromisoformat(case.today),
            )
        except Exception as exc:  # unexpected failure is an evaluation event
            observed_status = f"error: {type(exc).__name__}: {exc}"
            _mark(state, "data_sufficiency", False, f"data_sufficiency: {observed_status}")
            return _case_result(state, observed_status), _outcome(state)

        observed_status = str(plan.get("status", "unknown"))

        seen = json.dumps(plan, default=str)
        state["isolation"] = not any(marker in seen for marker in RECOMMENDATION_ISOLATION_MARKERS)
        _mark(state, "isolation", state["isolation"],
              "isolation: another user's records leaked into the plan")

        # -- data sufficiency: status must match the scenario's ground truth ---
        _mark(state, "data_sufficiency", plan.get("status") == case.expected_status,
              f"data_sufficiency: status expected {case.expected_status!r}, "
              f"observed {plan.get('status')!r}")

        expected = expected_plan(case.scenario, case.goal_amount, case.current_saved,
                                 case.target_date, case.today)
        recommendations = list(plan.get("recommendations") or [])
        expected_recs = list(case.expected_recommendations)

        # -- grounding: pinned fields and recommendation categories -------------
        for key, pinned in case.expected_fields:
            actual = plan.get(key, "<missing>")
            if pinned is None:
                _mark(state, "grounding", actual is None,
                      f"grounding: plan['{key}'] expected None, observed {actual!r}")
            else:
                actual_decimal, pinned_decimal = _decimal(actual), _decimal(pinned)
                if pinned_decimal is not None and actual_decimal is not None:
                    _mark(state, "grounding", actual_decimal == pinned_decimal,
                          f"grounding: plan['{key}'] expected {pinned_decimal}, "
                          f"observed {actual}")
                else:
                    _mark(state, "grounding", actual == pinned,
                          f"grounding: plan['{key}'] expected {pinned!r}, observed {actual!r}")
        _mark(state, "grounding", len(recommendations) == len(expected_recs),
              f"grounding: expected {len(expected_recs)} recommendation(s), "
              f"observed {len(recommendations)}")
        observed_by_category = {item.get("category"): item for item in recommendations}
        for category, spending, cut in expected_recs:
            observed_item = observed_by_category.get(category)
            if observed_item is None:
                _mark(state, "grounding", False,
                      f"grounding: no recommendation for category {category!r}")
                _mark(state, "arithmetic", False,
                      f"arithmetic: no recommendation for category {category!r} to check")
                _mark(state, "personalization", False,
                      f"personalization: no recommendation for category {category!r}")
                _mark(state, "estimate_labeling", False,
                      f"estimate_labeling: no recommendation for category {category!r}")
                continue
            _mark(state, "grounding", _within(observed_item.get("monthly_spending"), spending),
                  f"grounding: {category} monthly_spending expected {spending}, "
                  f"observed {observed_item.get('monthly_spending')!r}")

            # -- arithmetic: observed x fraction ~= cut within tolerance -------
            observed_cut = _decimal(observed_item.get("suggested_cut"))
            observed_spending = _decimal(observed_item.get("monthly_spending"))
            chain_cuts = {item_category: item_cut
                          for item_category, _, item_cut in expected["recommendations"]}
            chain_cut = chain_cuts.get(category)
            _mark(state, "arithmetic", chain_cut is not None and _within(observed_cut, chain_cut),
                  f"arithmetic: {category} suggested_cut expected {chain_cut}, "
                  f"observed {observed_cut} (tolerance {ARITHMETIC_TOLERANCE})")
            if observed_spending is not None and observed_cut is not None:
                cap = observed_spending * PLAN_REDUCTION_FRACTION + ARITHMETIC_TOLERANCE
                _mark(state, "arithmetic", Decimal("0") <= observed_cut <= cap,
                      f"arithmetic: {category} cut {observed_cut} is not a reduction of up to "
                      f"20% of the observed {observed_spending}")

            # -- personalization: amounts belong to this user's own spending ---
            average = category_monthly_averages(case.scenario).get(category)
            _mark(state, "personalization",
                  average is not None and average > 0
                  and _within(observed_item.get("monthly_spending"), average),
                  f"personalization: {category} does not match this user's actual "
                  f"monthly spending {average}")

            # -- estimate labeling: observed vs estimated are both present -----
            _mark(state, "estimate_labeling",
                  observed_item.get("monthly_spending") is not None
                  and observed_item.get("suggested_cut") is not None,
                  f"estimate_labeling: {category} must carry both the observed "
                  f"monthly_spending and the estimated suggested_cut")

        # -- no double counting: cuts must not exceed the monthly gap -----------
        cumulative = sum((_decimal(item.get("suggested_cut")) or Decimal("0")
                          for item in recommendations), Decimal("0"))
        categories = [item.get("category") for item in recommendations]
        _mark(state, "no_double_counting", len(categories) == len(set(categories)),
              f"no_double_counting: same category recommended twice ({categories})")
        if expected["estimated_monthly_surplus"] is not None:
            required = _decimal(expected["required_monthly_saving"]) or Decimal("0")
            surplus = _decimal(expected["estimated_monthly_surplus"]) or Decimal("0")
            deficit = max(Decimal("0"), required - surplus)
            _mark(state, "no_double_counting", cumulative <= deficit + ARITHMETIC_TOLERANCE,
                  f"no_double_counting: recommended cuts sum to {cumulative} but the "
                  f"monthly gap is only {deficit}")
        _mark(state, "no_double_counting",
              _within(plan.get("recommended_monthly_cut"),
                      sum((Decimal(cut) for _, _, cut in expected_recs), Decimal("0"))),
              "no_double_counting: recommended_monthly_cut does not equal the sum "
              "of the per-category cuts")

        # -- estimate labeling: plan-level behaviour ---------------------------
        limitations = list(plan.get("limitations") or [])
        _mark(state, "estimate_labeling", bool(limitations),
              "estimate_labeling: the plan reports no limitations")
        estimate_fields = ("estimated_monthly_income", "estimated_monthly_spending",
                           "estimated_monthly_surplus", "projected_monthly_saving")
        if case.expected_status == "insufficient_data":
            _mark(state, "estimate_labeling",
                  all(plan.get(field) is None for field in estimate_fields),
                  "estimate_labeling: insufficient-data plan fabricates numeric estimates")
            _mark(state, "no_double_counting", not recommendations,
                  "no_double_counting: insufficient-data plan still suggests cuts")
        else:
            _mark(state, "estimate_labeling",
                  all(plan.get(field) is not None for field in estimate_fields),
                  "estimate_labeling: data-backed plan hides its estimates")
        if case.limitation_contains:
            _mark(state, "data_sufficiency",
                  any(case.limitation_contains in line for line in limitations),
                  f"data_sufficiency: limitations do not mention "
                  f"{case.limitation_contains!r}")
    finally:
        clear_recommendation_scenarios(db, seeded)

    return _case_result(state, observed_status), _outcome(state)


def run_coach_case_with_outcome(db, case: CoachCase, as_of=RECOMMENDATION_AS_OF):
    """Evaluate one coach spending-reduction case against the blueprint."""
    from app.services.finance.coach import recommendations

    state = _new_case_state(case, "coach")
    seeded = seed_recommendation_scenarios(db, (case.scenario, CANARY_SCENARIO))
    derived = expected_coach_recommendations(case.scenario, as_of)
    adequate = case.scenario.history_months >= ADEQUATE_HISTORY_MONTHS
    try:
        user = seeded[0]
        try:
            payload = recommendations(db, user.id, as_of=as_of)
        except Exception as exc:
            _mark(state, "data_sufficiency", False,
                  f"data_sufficiency: recommendations crashed: "
                  f"{type(exc).__name__}: {exc}")
            return _case_result(state, "error"), _outcome(state)

        observed_items = list(payload.get("recommendations") or [])
        observed_status = "answered" if observed_items else "empty"

        seen = json.dumps(payload, default=str)
        state["isolation"] = not any(marker in seen for marker in RECOMMENDATION_ISOLATION_MARKERS)
        _mark(state, "isolation", state["isolation"],
              "isolation: another user's records leaked into the recommendations")

        # -- data sufficiency: recommendations exist only on adequate data -----
        expected = list(case.expected_recommendations)
        _mark(state, "data_sufficiency", len(observed_items) == len(expected),
              f"data_sufficiency: expected {len(expected)} recommendation(s), "
              f"observed {len(observed_items)}")
        if not adequate:
            limitations = list(payload.get("limitations") or [])
            _mark(state, "data_sufficiency",
                  bool(case.limitation_contains)
                  and any(case.limitation_contains in line for line in limitations),
                  f"data_sufficiency: inadequate history must be stated "
                  f"({case.limitation_contains!r})")
        else:
            _mark(state, "data_sufficiency",
                  not any("Three complete calendar months" in str(line)
                          for line in payload.get("limitations") or []),
                  "data_sufficiency: adequate history is flagged as inadequate")

        expected_by_category = {category: (saving, latest, previous)
                                for category, saving, latest, previous in expected}
        derived_by_category = {category: (saving, latest, previous)
                               for category, latest, previous, saving in derived}
        seen_categories: set[str] = set()
        seen_ids: set[str] = set()

        for observed_item in observed_items:
            category = observed_item.get("category")
            seen_categories.add(category)
            seen_ids.add(str(observed_item.get("id")))

            pinned = expected_by_category.get(category)
            _mark(state, "grounding", pinned is not None,
                  f"grounding: unexpected recommendation for category {category!r}")
            if pinned is None:
                continue
            saving, latest, previous = pinned
            evidence = observed_item.get("evidence") or {}

            _mark(state, "grounding",
                  _within(evidence.get("latest_expenses"), latest),
                  f"grounding: {category} latest_expenses expected {latest}, "
                  f"observed {evidence.get('latest_expenses')!r}")
            _mark(state, "grounding",
                  _within(evidence.get("previous_expenses"), previous),
                  f"grounding: {category} previous_expenses expected {previous}, "
                  f"observed {evidence.get('previous_expenses')!r}")
            title = str(observed_item.get("title", ""))
            _mark(state, "grounding", category in title,
                  f"grounding: title {title!r} does not name the actual category {category!r}")

            observed_saving = _decimal(observed_item.get("estimated_monthly_saving"))

            # -- arithmetic ----------------------------------------------------
            formula = min(Decimal(latest) * COACH_REDUCTION_FRACTION,
                          Decimal(latest) - Decimal(previous))
            _mark(state, "arithmetic", _within(observed_saving, formula),
                  f"arithmetic: {category} estimated saving expected {formula}, "
                  f"observed {observed_saving} (tolerance {ARITHMETIC_TOLERANCE})")
            _mark(state, "arithmetic",
                  _within(observed_item.get("estimated_annual_saving"),
                          (observed_saving or Decimal("0")) * 12),
                  f"arithmetic: {category} annual saving is not 12x the monthly estimate")
            _mark(state, "arithmetic",
                  observed_saving is not None
                  and Decimal("0") <= observed_saving
                  <= Decimal(latest) * COACH_REDUCTION_FRACTION + ARITHMETIC_TOLERANCE,
                  f"arithmetic: {category} saving {observed_saving} is not a "
                  f"reduction of up to 10% of the observed {latest}")

            # -- estimate labeling --------------------------------------------
            _mark(state, "estimate_labeling",
                  observed_item.get("estimated_monthly_saving") is not None
                  and observed_item.get("estimated_annual_saving") is not None,
                  f"estimate_labeling: {category} must label its amounts as estimates")
            assumptions = list(observed_item.get("assumptions") or [])
            _mark(state, "estimate_labeling", bool(assumptions),
                  f"estimate_labeling: {category} states no savings assumptions")
            _mark(state, "estimate_labeling",
                  observed_item.get("confidence") in {"low", "medium"},
                  f"estimate_labeling: {category} does not disclose its confidence")

            # -- personalization: the saving is derived from real user data ----
            derived_for_category = derived_by_category.get(category)
            _mark(state, "personalization",
                  derived_for_category is not None
                  and _within(observed_saving, derived_for_category[0]),
                  f"personalization: {category} saving does not derive from this "
                  f"user's own spending pattern")

        # -- no double counting ------------------------------------------------
        _mark(state, "no_double_counting", len(seen_categories) == len(observed_items),
              f"no_double_counting: one category is recommended twice "
              f"({seen_categories})")
        _mark(state, "no_double_counting", len(seen_ids) == len(observed_items),
              "no_double_counting: recommendation ids are not unique")
        # Each saving is capped by its own category's 10%; that plus category
        # distinctness is the structural no-double-counting contract: several
        # recommendations of overlapping spending must not be implied to be
        # additive beyond their per-category caps.
        for observed_item in observed_items:
            category = observed_item.get("category")
            pinned = expected_by_category.get(category)
            if pinned is None:
                continue
            observed_saving = _decimal(observed_item.get("estimated_monthly_saving"))
            _mark(state, "no_double_counting", observed_saving is not None
                  and observed_saving <= Decimal(pinned[1]) * COACH_REDUCTION_FRACTION
                  + ARITHMETIC_TOLERANCE,
                  f"no_double_counting: {category} saving {observed_saving} exceeds "
                  f"its per-category 10% cap")
    finally:
        clear_recommendation_scenarios(db, seeded)

    return _case_result(state, observed_status), _outcome(state)


def run_plan_case(db, case: PlanCase) -> CaseResult:
    result, _ = run_plan_case_with_outcome(db, case)
    return result


def run_coach_case(db, case: CoachCase) -> CaseResult:
    result, _ = run_coach_case_with_outcome(db, case)
    return result


def run_recommendation_dataset(db, as_of=None,
                               plan_cases: tuple[PlanCase, ...] = PLAN_CASES,
                               coach_cases: tuple[CoachCase, ...] = COACH_CASES):
    """Run every plan and coach case under freshly seeded, offline worlds."""
    from app.evaluation.recommendation_metrics import (
        RecommendationReport, summarize_recommendations,
    )

    as_of = as_of or RECOMMENDATION_AS_OF
    problems = validate_recommendation_dataset()
    if problems:
        raise ValueError("recommendation evaluation dataset is inconsistent: "
                         + "; ".join(problems))

    pairs = [run_plan_case_with_outcome(db, case) for case in plan_cases]
    pairs += [run_coach_case_with_outcome(db, case, as_of=as_of) for case in coach_cases]
    results = [result for result, _ in pairs]
    outcomes = [outcome for _, outcome in pairs]
    metrics = summarize_recommendations(outcomes, results, as_of)
    return RecommendationReport(as_of=as_of, case_count=len(results), results=results,
                                metrics=metrics, outcomes=outcomes)
