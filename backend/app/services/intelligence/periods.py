"""Central, timezone-safe calendar-period definitions (AI-13).

Every calendar computation inside the financial-intelligence engine derives
its windows here, so "current month", "previous complete month", the coach's
three-month history window and explicit ranges all share one implementation.

Conventions (matching the existing product):

* The product's calendar is Bangladesh's (``Asia/Dhaka``), matching
  ``finance.coach.today_dhaka`` and ``forecasting.cashflow``. ``today_dhaka``
  is re-exported here so callers have exactly one source.
* Boundaries are plain ``datetime.date`` objects; day-level inclusive
  semantics are carried explicitly (``start <= day <= end``) and no phase of
  day can change a result.
* A period records whether it is complete, so callers never re-derive
  "partial month" logic ad hoc.
* All functions are deterministic in ``as_of``: the same ``as_of`` must yield
  the same periods regardless of wall-clock time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

BANGLADESH_TIMEZONE = ZoneInfo("Asia/Dhaka")

# Period kinds.
CURRENT_MONTH = "current_month"
CALENDAR_MONTH = "calendar_month"
HISTORY_WINDOW = "history_window"
UPCOMING_HORIZON = "upcoming_horizon"
EXPLICIT_RANGE = "explicit_range"

DEFAULT_HISTORY_MONTHS = 3
DEFAULT_UPCOMING_HORIZON_DAYS = 30


def today_dhaka() -> date:
    """Use Bangladesh's calendar date for this Bangladesh-first product."""
    return datetime.now(BANGLADESH_TIMEZONE).date()


def money(value) -> Decimal:
    """Round money consistently to two decimal places (half-up)."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def month_shift(value: date, offset: int) -> date:
    """First day of the calendar month ``offset`` months from ``value``.

    Negative offsets go backwards and jump years correctly, so this is safe
    at year boundaries.
    """
    index = value.year * 12 + value.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def month_start(value: date) -> date:
    """First day of ``value``'s calendar month."""
    return value.replace(day=1)


def days_in_month(value: date) -> int:
    """Number of days in ``value``'s calendar month (year-boundary safe)."""
    next_month_start = month_shift(month_start(value), 1)
    return (next_month_start - timedelta(days=1)).day


def month_end(first_day: date) -> date:
    """Last day of the calendar month containing ``first_day``."""
    return month_shift(first_day, 1) - timedelta(days=1)


def month_key(value: date) -> str:
    """``YYYY-MM`` grouping key, lexicographically sortable."""
    return f"{value.year:04d}-{value.month:02d}"


@dataclass(frozen=True)
class Period:
    """An explicit, deterministic calendar window.

    ``start`` and ``end`` are inclusive. ``is_complete`` states whether every
    day of the window has already elapsed relative to the context date, so
    consumers can avoid strong historical claims on partial months.
    """

    kind: str
    start: date
    end: date
    is_complete: bool
    label: str

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError("Period start must not exceed end")

    @property
    def month_keys(self) -> list[str]:
        """Calendar-month keys covered by the period, oldest first."""
        keys: list[str] = []
        cursor = month_start(self.start)
        end_key = month_key(self.end)
        while True:
            key = month_key(cursor)
            keys.append(key)
            if key == end_key:
                return keys
            cursor = month_shift(cursor, 1)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "is_complete": self.is_complete,
            "label": self.label,
        }


def current_month_period(as_of: date) -> Period:
    """The running calendar month up to ``as_of`` (never flagged complete)."""
    start = month_start(as_of)
    return Period(
        kind=CURRENT_MONTH,
        start=start,
        end=as_of,
        is_complete=False,
        label=f"{month_key(as_of)} month to date (ends {month_end(start).isoformat()})",
    )


def calendar_month_period(first_day: date) -> Period:
    """One full calendar month given any date inside it."""
    start = month_start(first_day)
    end = month_end(start)
    return Period(
        kind=CALENDAR_MONTH,
        start=start,
        end=end,
        is_complete=True,
        label=month_key(start),
    )


def history_window_period(as_of: date, months: int = DEFAULT_HISTORY_MONTHS) -> Period:
    """``months`` complete calendar months ending with the month before ``as_of``.

    ``as_of`` itself never belongs to the window: the current month is
    incomplete and must not be averaged as if it were a full month.
    """
    start = month_shift(as_of, -months)
    end = month_shift(as_of, 0) - timedelta(days=1)
    return Period(
        kind=HISTORY_WINDOW,
        start=start,
        end=end,
        is_complete=True,
        label=f"{months} complete months to {month_key(end)}",
    )


def latest_complete_month_period(as_of: date) -> Period:
    """The most recent calendar month that has fully elapsed."""
    first = month_shift(as_of, -1)
    period = calendar_month_period(first)
    return Period(kind="latest_complete_month", start=period.start,
                  end=period.end, is_complete=True, label=f"latest complete month {period.label}")


def previous_complete_month_period(as_of: date, back: int = 2) -> Period:
    """The complete calendar month ``back - 1`` months before ``as_of``'s month."""
    first = month_shift(as_of, -back)
    period = calendar_month_period(first)
    return Period(kind="previous_complete_month", start=period.start,
                  end=period.end, is_complete=True, label=f"previous complete month {period.label}")


def upcoming_period(as_of: date, days: int = DEFAULT_UPCOMING_HORIZON_DAYS) -> Period:
    """A forward-looking horizon starting today (inclusive)."""
    return Period(
        kind=UPCOMING_HORIZON,
        start=as_of,
        end=as_of + timedelta(days=days),
        is_complete=False,
        label=f"next {days} days",
    )


def explicit_period(start: date, end: date, anchor: date | None = None) -> Period:
    """An arbitrary inclusive date range supplied by a caller.

    ``is_complete`` compares the range against ``anchor`` (defaults to
    today in Dhaka): the window is complete only once every day has passed.
    """
    anchor = anchor or today_dhaka()
    return Period(
        kind=EXPLICIT_RANGE,
        start=start,
        end=end,
        is_complete=end < anchor,
        label=f"{start.isoformat()} to {end.isoformat()}",
    )
