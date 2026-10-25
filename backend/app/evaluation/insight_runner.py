"""AI-12D runner: proactive insights against controlled scenario ground truth.

Execution flow per case:
    seeded scenario (+ isolation canary) -> nudges(as_of=fixed) -> insights
    -> per-dimension scores (presence, numbers, dates, plan_labeling,
    isolation) -> CaseResult + InsightOutcome.

The system under test is judged on structured financial claims only: whether
an insight exists when the scenario condition is true, is absent when it is
false, carries the pinned ground-truth numbers and dates, marks scheduled
obligations as plans rather than actuals, and never leaks another user's
records.  Natural-language wording is never compared.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from app.evaluation.datasets.insight_scenarios import (
    CANARY_SCENARIO,
    INSIGHT_AS_OF,
    INSIGHT_EVALUATION_CASES,
    INSIGHT_ISOLATION_MARKERS,
    InsightCase,
    clear_insight_scenarios,
    seed_insight_scenarios,
    validate_insight_dataset,
)
from app.evaluation.metrics import CaseResult

#: Dimensions scored for the insight evaluation.
INSIGHT_SCORE_DIMENSIONS = ("presence", "numbers", "dates", "plan_labeling", "isolation")

NOT_AN_ACTUAL_PHRASE = "not an actual transaction"
PLAN_MARKER_FIELD = "record_type"
PLAN_MARKER_VALUE = "plan"


def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _as_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _expectation_holds(evidence: dict, path: str, expected: str) -> bool:
    raw = evidence.get(path)
    if expected == "!non_null":
        return raw is not None
    observed, wanted = _decimal(raw), _decimal(expected)
    if observed is not None and wanted is not None:
        return observed == wanted
    return str(raw) == str(expected)


def run_insight_case(db, case: InsightCase, as_of=INSIGHT_AS_OF) -> CaseResult:
    """Seed one controlled world and score the nudges response against it."""
    result, _ = run_insight_case_with_outcome(db, case, as_of=as_of)
    return result


def run_insight_case_with_outcome(db, case: InsightCase, as_of=INSIGHT_AS_OF):
    """Score one case and return (CaseResult, InsightOutcome for the metrics)."""
    from app.evaluation.insight_metrics import InsightOutcome

    expected_status = "triggered" if any(spec.count > 0 for spec in case.expected) else "absent"
    scores: dict[str, float | None] = {dimension: None for dimension in INSIGHT_SCORE_DIMENSIONS}
    failures: list[str] = []
    counters = {"numbers": [0, 0], "dates": [0, 0], "plan_labeling": [0, 0]}  # [checks, passed]
    type_results: dict[str, str] = {}
    unexpected_types = [0]
    isolation_state = [True]

    counters_on = {"numbers", "dates", "plan_labeling"}

    def mark(dimension: str, ok: bool, message: str, applies: bool = True):
        if not applies:
            return
        if dimension in counters_on:
            counters[dimension][0] += 1
            if ok:
                counters[dimension][1] += 1
        if ok:
            scores[dimension] = 1.0 if scores[dimension] is None else scores[dimension]
        else:
            scores[dimension] = 0.0
            failures.append(message)

    from app.services.finance.coach import nudges

    seeded = seed_insight_scenarios(db, (case.scenario, CANARY_SCENARIO))
    observed_status = "error"
    try:
        try:
            payload = nudges(db, seeded[0].id, as_of=as_of)
        except Exception as exc:  # an error is an evaluation event, not a crash
            payload = None
            observed_status = f"error: {type(exc).__name__}: {exc}"

        items = list((payload or {}).get("insights") or [])

        # -- isolation: canary content must never cross user boundaries --------
        seen = json.dumps(payload, default=str) if payload is not None else ""
        leak = any(marker in seen for marker in INSIGHT_ISOLATION_MARKERS)
        isolation_state[0] = not leak
        mark("isolation", not leak, "isolation: another user's records leaked into the insights")

        if payload is None:
            mark("presence", False, f"presence: nudges raised {observed_status}")
            for spec in case.expected:
                type_results[spec.type] = "fn" if spec.count > 0 else "tn"
            observed_status = observed_status if observed_status != "triggered" else "error"
            return _case_result(case, expected_status, observed_status, scores, failures), _outcome(
                case, expected_status, observed_status, scores, failures,
                counters, type_results, isolation_state, unexpected_types)

        declared = {spec.type for spec in case.expected}
        unexpected = sorted({item.get("type") for item in items} - declared)
        unexpected_types[0] = len(unexpected)
        if unexpected:
            mark("presence", False,
                 f"presence: insight types {unexpected} were not declared by the scenario")

        any_expected_present = any(
            spec.count > 0 and item.get("type") == spec.type
            for item in items for spec in case.expected)
        observed_status = "triggered" if any_expected_present else "absent"

        # -- per-type structured expectations ----------------------------------
        for spec in case.expected:
            where = spec.type
            matches = [item for item in items if item.get("type") == spec.type]
            detected = len(matches) == spec.count

            mark("presence", detected,
                 f"presence: {where} expected {spec.count} insight(s), observed {len(matches)}")
            # Verdict for the detection matrix: presence condition truth comes
            # from the scenario spec (count > 0), matching comes from the run.
            type_results[where] = (
                ("tp" if spec.count > 0 else "tn")
                if detected else ("fn" if spec.count > 0 else "fp"))

            remaining = list(matches)
            for number, evidence_set in enumerate(spec.evidence_sets, start=1):
                set_label = f"{where}: evidence set #{number}"
                chosen = next(
                    (candidate for candidate in remaining
                     if all(_expectation_holds(candidate.get("evidence") or {},
                                               path, expected)
                            for path, expected in evidence_set)),
                    None)
                if chosen is None:
                    details: list[str] = []
                    for candidate in remaining:
                        evidence = candidate.get("evidence") or {}
                        details.extend(
                            f"evidence['{path}'] expected {expected!r}, "
                            f"observed {evidence.get(path, '<missing>')!r}"
                            for path, expected in evidence_set
                            if not _expectation_holds(evidence, path, expected))
                    mark("numbers", False,
                         (set_label + " matched no observed insight: " + "; ".join(details))
                         if details else (set_label + " matched no observed insight"))
                    if spec.period or spec.expires_on:
                        mark("dates", False, f"{set_label}: no insight to check pinned dates")
                    if spec.plan_marked:
                        mark("plan_labeling", False,
                             f"{set_label}: no insight to check the plan marking")
                    continue

                remaining.remove(chosen)
                evidence = chosen.get("evidence") or {}

                # -- numbers: structured financial claims ----------------------
                for path, expected in evidence_set:
                    raw = evidence.get(path)
                    if expected == "!non_null":
                        mark("numbers", raw is not None, f"{where}: evidence['{path}'] is missing")
                    else:
                        observed, wanted = _decimal(raw), _decimal(expected)
                        if observed is not None and wanted is not None:
                            mark("numbers", observed == wanted,
                                 f"{where}: evidence['{path}'] expected {wanted}, observed {observed}")
                        else:
                            mark("numbers", str(raw) == str(expected),
                                 f"{where}: evidence['{path}'] expected {expected!r}, observed {raw!r}")

                # -- dates ------------------------------------------------------
                if spec.period:
                    wanted_period = tuple(date.fromisoformat(value) for value in spec.period)
                    observed_period = (_as_date(chosen.get("period_start")),
                                       _as_date(chosen.get("period_end")))
                    mark("dates", observed_period == wanted_period,
                         f"{where}: period expected {wanted_period}, observed {observed_period}")
                if spec.expires_on:
                    wanted_expiry = date.fromisoformat(spec.expires_on)
                    observed_expiry = _as_date(chosen.get("expires_on"))
                    mark("dates", observed_expiry == wanted_expiry,
                         f"{where}: expires_on expected {wanted_expiry}, observed {observed_expiry}")

                # -- scheduled != actual ------------------------------------------
                if spec.plan_marked:
                    mark("plan_labeling", evidence.get(PLAN_MARKER_FIELD) == PLAN_MARKER_VALUE,
                         f"{where}: scheduled obligation is not marked as a plan "
                         f"(evidence['{PLAN_MARKER_FIELD}'] != {PLAN_MARKER_VALUE!r})")
                    mark("plan_labeling",
                         NOT_AN_ACTUAL_PHRASE in str(chosen.get("next_action", "")),
                         f"{where}: next_action does not state the schedule is {NOT_AN_ACTUAL_PHRASE!r}")
    finally:
        clear_insight_scenarios(db, seeded)

    result = _case_result(case, expected_status, observed_status, scores, failures)
    outcome = _outcome(case, expected_status, observed_status, scores, failures,
                       counters, type_results, isolation_state, unexpected_types)
    return result, outcome


def _case_result(case: InsightCase, expected_status: str, observed_status: str,
                 scores: dict, failures: list[str]) -> CaseResult:
    return CaseResult(case_id=case.case_id, group=case.behavior,
                      expected_status=expected_status, observed_status=observed_status,
                      scores=scores, failures=failures)


def _outcome(case: InsightCase, expected_status: str, observed_status: str,
             scores: dict, failures: list[str], counters: dict,
             type_results: dict, isolation_state: list, unexpected_types: list):
    from app.evaluation.insight_metrics import InsightOutcome

    return InsightOutcome(
        case_id=case.case_id,
        behavior=case.behavior,
        expected_status=expected_status,
        observed_status=observed_status,
        type_results=type_results,
        numeric_checks=counters["numbers"][0],
        numeric_passed=counters["numbers"][1],
        date_checks=counters["dates"][0],
        date_passed=counters["dates"][1],
        plan_checks=counters["plan_labeling"][0],
        plan_passed=counters["plan_labeling"][1],
        isolation_ok=isolation_state[0],
        unexpected_types=unexpected_types[0],
    )


def run_insight_dataset(db, as_of=None, cases: tuple[InsightCase, ...] = INSIGHT_EVALUATION_CASES):
    """Run every insight case under a freshly seeded, fully offline world."""
    from app.evaluation.insight_metrics import InsightReport, summarize_insights

    as_of = as_of or INSIGHT_AS_OF
    problems = validate_insight_dataset()
    if problems:
        raise ValueError("insight evaluation dataset is inconsistent: " + "; ".join(problems))

    pairs = [run_insight_case_with_outcome(db, case, as_of=as_of) for case in cases]
    results = [result for result, _ in pairs]
    outcomes = [outcome for _, outcome in pairs]
    metrics = summarize_insights(outcomes, results, as_of)
    return InsightReport(as_of=as_of, case_count=len(results), results=results,
                         metrics=metrics, outcomes=outcomes)
