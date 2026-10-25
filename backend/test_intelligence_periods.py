"""AI-13 tests: central period semantics.

Period boundaries must be deterministic, timezone-safe, explicit about
inclusive ends and completeness, and correct at year boundaries.
"""
from datetime import date

import pytest

from app.services.intelligence.periods import (
    Period,
    calendar_month_period,
    current_month_period,
    days_in_month,
    explicit_period,
    history_window_period,
    latest_complete_month_period,
    month_end,
    month_key,
    month_shift,
    month_start,
    previous_complete_month_period,
    upcoming_period,
)


def test_month_shift_is_year_boundary_safe():
    assert month_shift(date(2026, 12, 15), 1) == date(2027, 1, 1)
    assert month_shift(date(2027, 1, 15), -1) == date(2026, 12, 1)
    assert month_shift(date(2026, 10, 25), -3) == date(2026, 7, 1)
    assert month_shift(date(2027, 2, 1), -2) == date(2026, 12, 1)


def test_month_start_end_and_keys():
    assert month_start(date(2026, 10, 25)) == date(2026, 10, 1)
    assert month_end(date(2026, 10, 25)) == date(2026, 10, 31)
    assert month_end(date(2028, 2, 10)) == date(2028, 2, 29)  # leap year
    assert month_key(date(2026, 10, 25)) == "2026-10"


def test_days_in_month():
    assert days_in_month(date(2026, 10, 25)) == 31
    assert days_in_month(date(2026, 2, 1)) == 28
    assert days_in_month(date(2028, 2, 1)) == 29


def test_current_month_period_is_partial_and_inclusive():
    period = current_month_period(date(2026, 10, 25))
    assert period.start == date(2026, 10, 1)
    assert period.end == date(2026, 10, 25)
    assert period.is_complete is False
    assert period.to_dict()["end"] == "2026-10-25"


def test_current_month_period_covers_the_whole_month_on_a_month_end():
    period = current_month_period(date(2026, 10, 31))
    assert (period.start, period.end) == (date(2026, 10, 1), date(2026, 10, 31))
    # Still not marked complete: only an explicit complete month claims that.
    assert period.is_complete is False


def test_calendar_month_period_is_complete():
    period = calendar_month_period(date(2026, 10, 3))
    assert (period.start, period.end) == (date(2026, 10, 1), date(2026, 10, 31))
    assert period.is_complete is True
    assert period.month_keys == ["2026-10"]


def test_history_window_excludes_the_current_month():
    period = history_window_period(date(2026, 10, 25), months=3)
    assert (period.start, period.end) == (date(2026, 7, 1), date(2026, 9, 30))
    assert period.is_complete is True
    assert period.month_keys == ["2026-07", "2026-08", "2026-09"]


def test_history_window_across_a_year_boundary():
    period = history_window_period(date(2027, 1, 31), months=3)
    assert (period.start, period.end) == (date(2026, 10, 1), date(2026, 12, 31))
    assert period.month_keys == ["2026-10", "2026-11", "2026-12"]


def test_complete_month_constructors():
    assert latest_complete_month_period(date(2026, 10, 25)).start == date(2026, 9, 1)
    assert latest_complete_month_period(date(2026, 10, 25)).end == date(2026, 9, 30)
    assert previous_complete_month_period(date(2026, 10, 25)).start == date(2026, 8, 1)
    assert previous_complete_month_period(date(2026, 10, 25)).end == date(2026, 8, 31)


def test_upcoming_period_contains_today_and_horizon():
    period = upcoming_period(date(2026, 10, 25), days=30)
    assert (period.start, period.end) == (date(2026, 10, 25), date(2026, 11, 24))
    assert period.month_keys == ["2026-10", "2026-11"]


def test_explicit_period_completeness_depends_only_on_the_anchor():
    complete = explicit_period(date(2026, 1, 1), date(2026, 1, 31), anchor=date(2026, 10, 25))
    running = explicit_period(date(2026, 10, 1), date(2026, 10, 25), anchor=date(2026, 10, 25))
    assert complete.is_complete is True
    assert running.is_complete is False
    assert running.end == running.end  # inclusive end is part of the window


def test_empty_or_reversed_range_is_rejected():
    with pytest.raises(ValueError):
        explicit_period(date(2026, 10, 25), date(2026, 10, 1), anchor=date(2026, 10, 25))
    with pytest.raises(ValueError):
        Period(kind="x", start=date(2026, 10, 2), end=date(2026, 10, 1),
               is_complete=False, label="invalid")


def test_same_as_of_produces_identical_periods():
    assert current_month_period(date(2026, 3, 17)) == current_month_period(date(2026, 3, 17))
    assert history_window_period(date(2026, 3, 17), 3).month_keys == \
        history_window_period(date(2026, 3, 17), 3).month_keys
