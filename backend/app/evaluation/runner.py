"""Evaluation runner for the deterministic finance coach.

Execution flow per case:
    seeded scenario -> answer_question(as_of=fixed) -> structured response
    -> per-dimension scores (intent, dates, numerics, status, grounding,
    safety/isolation) -> CaseResult -> EvaluationReport.

No LLM provider and no network is involved. Ambiguous questions are caught
and scored as the coach refusing to guess rather than an error.
"""
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.schemas.chat import FinanceQuestionRequest
from app.services.finance.grounded_chat import AmbiguousQuestion, answer_question
from app.evaluation.datasets.finance_scenario import (
    AS_OF,
    EVALUATION_SCENARIO,
    ISOLATION_CANARY,
    scenario_totals,
    seed_scenario,
    clear_scenario,
)
from app.evaluation.datasets.finance_questions import EVALUATION_CASES
from app.evaluation.datasets.grounded_chat_stress import STRESS_CASES
from app.evaluation.metrics import (
    SCORE_DIMENSIONS,
    CaseResult,
    EvaluationReport,
    summarize,
    format_report,
)


def resolve_date_marker(marker, as_of, months_ahead: int = 3):
    """Turn a dataset date-range marker into an expected (start, end) pair.

    Markers are resolved independently of the coach, using calendar arithmetic
    copied from the product contract (month start/end, equal-day comparison
    windows). Returns None for markers that expect no date range.
    """
    if marker is None:
        return None
    mode = marker.get("mode")
    if mode == "current_month_to_today":
        return as_of.replace(day=1), as_of
    if mode == "previous_month_full":
        index = as_of.year * 12 + as_of.month - 2
        start = date(index // 12, index % 12 + 1, 1)
        return start, date(as_of.year, as_of.month, 1) - timedelta(days=1)
    if mode == "previous_month_matched":
        start = date(as_of.year, as_of.month, 1) - timedelta(days=1)
        start = start.replace(day=1)
        end = min(start + timedelta(days=as_of.day - 1), date(as_of.year, as_of.month, 1) - timedelta(days=1))
        return start, end
    if mode == "last_n_days":
        return as_of - timedelta(days=marker["days"]), as_of
    if mode == "today_plus":
        return as_of, as_of + timedelta(days=marker["days"])
    if mode == "explicit":
        return date.fromisoformat(marker["start"]), date.fromisoformat(marker["end"])
    if mode == "history_window":
        index = as_of.year * 12 + as_of.month - 1 - 3
        start = date(index // 12, index % 12 + 1, 1)
        return start, date(as_of.year, as_of.month, 1) - timedelta(days=1)
    if mode == "forecast_horizon":
        index = as_of.year * 12 + as_of.month - 1 + marker.get("months_ahead", 3)
        return as_of, date(index // 12, index % 12 + 1, 1) - timedelta(days=1)
    raise ValueError(f"Unknown date marker mode: {mode!r}")


def _path_value(payload, path: str, default=None):
    current = payload
    for part in path.split("."):
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return default
            current = current[index]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _resolve_ground_truth_range(range_spec, as_of):
    marker = range_spec.get("range", range_spec)
    return resolve_date_marker(marker, as_of)


# Fixed evaluation "today"; every case is executed with this as_of so results
# are month-shape-stable regardless of the real calendar date.
EVALUATION_SCENARIO_AS_OF = AS_OF

# Full campaign: AI-12A foundation cases + AI-12B stress cases.
ALL_CASES = list(EVALUATION_CASES) + list(STRESS_CASES)


def ground_truth_consistency(scenario=EVALUATION_SCENARIO, as_of=None) -> list[str]:
    """Cross-check dataset numbers against scenario-derived totals.

    This evaluates the dataset itself: numeric expectations pinned in case
    definitions must equal totals recomputed with plain arithmetic from the
    seed specification, independent of the coach's SQL path.
    """
    as_of = as_of or EVALUATION_SCENARIO_AS_OF
    problems = []
    for case in ALL_CASES:
        for block in case.get("ground_truth_check", []):
            span = _resolve_ground_truth_range(block, as_of)
            if span is None:
                problems.append(f"{case['id']}: ground truth range did not resolve: {block}")
                continue
            start, end = span
            totals = scenario_totals(
                scenario, block.get("user_index", 0), start, end,
                block.get("category"))
            for metric, expected in (("expenses", block.get("expenses")),
                                     ("income", block.get("income"))):
                if expected is None:
                    continue
                if totals[metric] != _decimal(expected):
                    problems.append(
                        f"{case['id']}: ground truth {metric} for {start}..{end}"
                        f" is {totals[metric]}, dataset says {expected}")
    return problems


def run_case(db, case: dict, user_a, user_b, as_of) -> CaseResult:
    """Execute one evaluation case and score all applicable dimensions."""
    expected_status = case.get("expected_status", "answered")
    result = None
    observed_status = "error"
    try:
        payload = FinanceQuestionRequest(
            question=case["question"],
            **case.get("payload", {}))
        result = answer_question(db, user_a.id, payload, as_of=as_of)
        observed_status = result.get("status", "answered")
    except AmbiguousQuestion:
        observed_status = "ambiguous"
    except Exception as exc:  # unexpected failure is an evaluation event, not a crash
        observed_status = f"error: {type(exc).__name__}: {exc}"

    scores: dict[str, float | None] = {dimension: None for dimension in SCORE_DIMENSIONS}
    failures: list[str] = []

    def mark(dimension: str, ok: bool, message: str, applies: bool = True):
        if not applies:
            return
        if ok:
            scores[dimension] = 1.0 if scores[dimension] is None else scores[dimension]
        else:
            scores[dimension] = 0.0
            failures.append(message)

    # -- status ------------------------------------------------------------
    mark("status", observed_status == expected_status,
         f"status: expected {expected_status!r}, observed {observed_status!r}")

    # -- ambiguous cases: refusal itself is the safe behaviour --------------
    if expected_status == "ambiguous":
        mark("safety", result is None,
             "safety: ambiguous question produced a fabricated answer instead of refusing")
    elif result is None:
        # Cannot score further without a response.
        pass
    else:
        # -- safety: user isolation / leaked data ++ fabricated numerics ----
        # The isolation canary only applies when asking as the honest user
        # (the canary merchant legitimately appears in its owner's answers).
        is_canary_check = case.get("user_index", 0) == 0
        leak = is_canary_check and ISOLATION_CANARY in json.dumps(result, default=str)
        mark("safety", not leak, "safety: another user's records leaked into the answer")
        if observed_status == "insufficient_data":
            mark("safety", "BDT" not in result.get("answer", ""),
                 "safety: insufficient-data answer fabricates a numeric total")

        # -- intent ---------------------------------------------------------
        expected_intent = case.get("expected_intent")
        mark("intent", result.get("intent") == expected_intent,
             f"intent: expected {expected_intent!r}, observed {result.get('intent')!r}",
             expected_intent is not None)

        # -- date range -----------------------------------------------------
        marker = case.get("expected_date_range")
        if marker is None:
            mark("date", result.get("date_range") is None,
                 f"date: expected no date_range, observed {result.get('date_range')!r}")
        else:
            expected_span = resolve_date_marker(marker, as_of)
            observed_span = result.get("date_range")
            if expected_span is None:
                mark("date", observed_span is None,
                     f"date: expected no date_range, observed {observed_span!r}")
            else:
                if observed_span is None:
                    mark("date", False, f"date: expected {expected_span}, observed None")
                else:
                    observed_dates = (
                        date.fromisoformat(str(observed_span["start_date"])),
                        date.fromisoformat(str(observed_span["end_date"])))
                    mark("date", observed_dates == expected_span,
                         f"date: expected {expected_span}, observed {observed_dates}")

        # -- numeric / structured calculation fields -------------------------
        expectations = case.get("expected_calculation") or {}
        for path, expected in sorted(expectations.items()):
            actual = _path_value(result.get("calculation", {}), path)
            if isinstance(expected, str) and expected == "!non_null":
                mark("numeric", actual is not None,
                     f"numeric: calculation['{path}'] is missing")
            elif isinstance(expected, str) and expected == "!missing":
                mark("numeric", actual is None,
                     f"numeric: calculation['{path}'] unexpectedly present: {actual!r}")
            elif isinstance(expected, str):
                expected_decimal = _decimal(expected)
                if expected_decimal is not None and _decimal(actual) is not None:
                    mark("numeric", _decimal(actual) == expected_decimal,
                         f"numeric: calculation['{path}'] expected {expected_decimal}, observed {actual}")
                else:
                    mark("numeric", actual == expected,
                         f"numeric: calculation['{path}'] expected {expected!r}, observed {actual!r}")
            else:
                mark("numeric", actual == expected,
                     f"numeric: calculation['{path}'] expected {expected!r}, observed {actual!r}")

        # -- grounding: structured evidence must exist and stay consistent --
        if observed_status == "answered":
            mark("grounding", bool(result.get("answer")),
                 "grounding: answered case has no answer text")
            ground_truth_numbers = [str(number) for number in case.get("answer_must_contain", [])]
            text = result.get("answer", "")
            for number in ground_truth_numbers:
                mark("grounding", number in text,
                     f"grounding: answer text does not contain the reported amount {number}")
            # The distinction between plans and actual records must be stated.
            mark("grounding", result.get("coverage") or result.get("sources")
                 or result.get("calculation", {}).get("operation"),
                 "grounding: answered case cites no sources, coverage, or operation")

    return CaseResult(case_id=case["id"], group=case["group"],
                      expected_status=expected_status,
                      observed_status=observed_status,
                      scores=scores, failures=failures)


def run_dataset(db, as_of=None, scenario=EVALUATION_SCENARIO) -> EvaluationReport:
    as_of = as_of or EVALUATION_SCENARIO_AS_OF
    users = seed_scenario(db, scenario)
    try:
        user_a, user_b = users[0], users[-1]
        results = [run_case(db, case,
                            users[case.get("user_index", 0)], user_b, as_of)
                   for case in ALL_CASES]
    finally:
        clear_scenario(db, users)
    metrics = summarize(results, as_of)
    return EvaluationReport(as_of=as_of, case_count=len(results),
                            results=results, metrics=metrics)
