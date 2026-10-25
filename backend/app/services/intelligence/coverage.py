"""Data-coverage awareness: what the records can and cannot support (AI-13).

Financial arithmetic must never silently over-claim. This module turns raw
"which calendar months have records" information into an explicit coverage
status so every consumer can see:

* whether any records exist at all,
* whether history covers the required complete calendar months,
* how much of the current month is still missing.

The empty-month and partial-month ``status`` values deliberately read as
information, not failure: "insufficient_history" tells a consumer to soften
its claims, not to fabricate zeros for the missing months.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from app.services.intelligence.periods import (
    Period,
    month_key,
)

STATUS_NO_RECORDS = "no_records"
STATUS_PARTIAL_ONLY = "partial_current_only"
STATUS_INSUFFICIENT = "insufficient_history"
STATUS_ADEQUATE = "adequate_history"

#: Verbatim from deterministic coaching; regression suites pin the string.
INSUFFICIENT_HISTORY_LIMITATION = (
    "Three complete calendar months with observed records are required; "
    "missing months are unknown."
)
NO_RECORDS_LIMITATION = (
    "No transaction records cover the expected months; financial totals are unknown."
)
PARTIAL_ONLY_LIMITATION = (
    "Only the current, incomplete month has records; comparisons with a normal "
    "month are not supported yet."
)


@dataclass(frozen=True)
class DataCoverage:
    """Structured statement of what data backs one period's calculations."""

    period: Period
    as_of: date
    months_expected_complete: int
    complete_months_observed: tuple[str, ...]
    partial_months_observed: tuple[str, ...]
    months_observed: tuple[str, ...]
    status: str
    is_adequate: bool
    limitations: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "period": self.period.to_dict(),
            "as_of": self.as_of.isoformat(),
            "months_expected_complete": self.months_expected_complete,
            "complete_months_observed": list(self.complete_months_observed),
            "partial_months_observed": list(self.partial_months_observed),
            "months_observed": list(self.months_observed),
            "status": self.status,
            "is_adequate": self.is_adequate,
            "limitations": list(self.limitations),
        }


def _calendar_month_is_complete(first_day: date, as_of: date) -> bool:
    """A calendar month is complete once the whole month has elapsed."""
    return month_key(first_day) < month_key(as_of)


def assess_coverage(
    period: Period,
    months_with_records: Iterable[str],
    as_of: date,
    required_complete_months: int | None = None,
) -> DataCoverage:
    """Classify how well one period's calendar months are covered.

    ``months_with_records`` holds ``YYYY-MM`` keys of calendar months that
    contain at least one record. Only months inside ``period`` count; a month
    counts as *observed-complete* when its records already exist for a month
    that has fully elapsed, and as *partial* when its records are still
    arriving (`month_key(as_of)`).
    """
    observed = {key for key in months_with_records} & {key for key in period.month_keys}
    observed = sorted(observed)
    current_key = month_key(as_of)

    complete = tuple(key for key in observed if _calendar_month_is_complete(
        _first_day(key), as_of))
    partial = tuple(key for key in observed if key >= current_key)

    required = required_complete_months or len(complete)

    if not observed:
        status = STATUS_NO_RECORDS
        limitations = (NO_RECORDS_LIMITATION,)
    elif not complete:
        status = STATUS_PARTIAL_ONLY
        limitations = (PARTIAL_ONLY_LIMITATION,)
    elif len(complete) < required:
        status = STATUS_INSUFFICIENT
        limitations = (INSUFFICIENT_HISTORY_LIMITATION,)
    else:
        status = STATUS_ADEQUATE
        limitations = ()

    return DataCoverage(
        period=period,
        as_of=as_of,
        months_expected_complete=required,
        complete_months_observed=complete,
        partial_months_observed=partial,
        months_observed=tuple(observed),
        status=status,
        is_adequate=status == STATUS_ADEQUATE,
        limitations=limitations,
    )


def _first_day(month_key_value: str) -> date:
    year, month = (int(part) for part in month_key_value.split("-"))
    return date(year, month, 1)
