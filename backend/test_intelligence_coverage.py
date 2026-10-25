"""AI-13 tests: data-coverage classification.

The engine must never make strong historical claims without enough history:
zero records, one month, partial current months and adequate history all have
distinct, structured outcomes with explicit limitations.
"""
from datetime import date

from app.services.intelligence.coverage import (
    INSUFFICIENT_HISTORY_LIMITATION,
    NO_RECORDS_LIMITATION,
    PARTIAL_ONLY_LIMITATION,
    STATUS_ADEQUATE,
    STATUS_INSUFFICIENT,
    STATUS_NO_RECORDS,
    STATUS_PARTIAL_ONLY,
    assess_coverage,
)
from app.services.intelligence.periods import (
    current_month_period,
    history_window_period,
)


def test_no_records_reports_unknown_not_zero():
    coverage = assess_coverage(
        history_window_period(date(2026, 10, 25)), [], date(2026, 10, 25),
        required_complete_months=3)
    assert coverage.status == STATUS_NO_RECORDS
    assert coverage.is_adequate is False
    assert coverage.limitations == (NO_RECORDS_LIMITATION,)
    assert coverage.months_observed == ()


def test_one_complete_month_is_insufficient_for_three_month_claims():
    coverage = assess_coverage(
        history_window_period(date(2026, 10, 25)),
        ["2026-08"], date(2026, 10, 25), required_complete_months=3)
    assert coverage.status == STATUS_INSUFFICIENT
    assert coverage.limitations == (INSUFFICIENT_HISTORY_LIMITATION,)
    assert coverage.complete_months_observed == ("2026-08",)


def test_two_complete_months_stay_insufficient():
    coverage = assess_coverage(
        history_window_period(date(2026, 10, 25)),
        ["2026-08", "2026-09"], date(2026, 10, 25), required_complete_months=3)
    assert coverage.status == STATUS_INSUFFICIENT
    assert coverage.is_adequate is False


def test_adequate_history_needs_every_window_month():
    coverage = assess_coverage(
        history_window_period(date(2026, 10, 25)),
        ["2026-07", "2026-08", "2026-09"], date(2026, 10, 25),
        required_complete_months=3)
    assert coverage.status == STATUS_ADEQUATE
    assert coverage.is_adequate is True
    assert coverage.limitations == ()


def test_adequate_history_ignores_months_outside_the_window():
    # Records outside the window (June) do not make the window adequate.
    coverage = assess_coverage(
        history_window_period(date(2026, 10, 25)),
        ["2026-06", "2026-08", "2026-09"], date(2026, 10, 25),
        required_complete_months=3)
    assert coverage.status == STATUS_INSUFFICIENT
    assert coverage.months_observed == ("2026-08", "2026-09")


def test_partial_current_month_only_is_explicitly_not_comparable():
    coverage = assess_coverage(
        current_month_period(date(2026, 10, 25)),
        ["2026-10"], date(2026, 10, 25))
    assert coverage.status == STATUS_PARTIAL_ONLY
    assert coverage.is_adequate is False
    assert coverage.limitations == (PARTIAL_ONLY_LIMITATION,)
    assert coverage.partial_months_observed == ("2026-10",)


def test_empty_current_month_is_no_records():
    coverage = assess_coverage(
        current_month_period(date(2026, 10, 25)), [], date(2026, 10, 25))
    assert coverage.status == STATUS_NO_RECORDS
    assert coverage.limitations == (NO_RECORDS_LIMITATION,)


def test_coverage_to_dict_is_serializable_and_explicit():
    coverage = assess_coverage(
        history_window_period(date(2026, 10, 25)),
        ["2026-07", "2026-08", "2026-09"], date(2026, 10, 25),
        required_complete_months=3)
    payload = coverage.to_dict()
    assert payload["status"] == STATUS_ADEQUATE
    assert payload["is_adequate"] is True
    assert payload["complete_months_observed"] == ["2026-07", "2026-08", "2026-09"]
    assert payload["period"]["is_complete"] is True
