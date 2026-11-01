"""Deterministic notification eligibility service.

Evaluates notification delivery eligibility based on user preferences,
alert severity, delivery channel, quiet hours, consent, and frequency policy.
Never involves AI/LLMs or non-deterministic logic.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.notification_preference import NotificationPreference

SEVERITY_ORDER: dict[str, int] = {
    "info": 10,
    "low": 20,
    "medium": 30,
    "warning": 30,
    "high": 40,
    "critical": 50,
}


class EligibilityReason(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    DISABLED = "DISABLED"
    BELOW_SEVERITY_THRESHOLD = "BELOW_SEVERITY_THRESHOLD"
    QUIET_HOURS = "QUIET_HOURS"
    NO_CONSENT = "NO_CONSENT"
    ALREADY_DELIVERED = "ALREADY_DELIVERED"
    FREQUENCY_SUPPRESSED = "FREQUENCY_SUPPRESSED"


@dataclass(frozen=True)
class EligibilityResult:
    is_eligible: bool
    reason: EligibilityReason
    next_eligible_at: datetime | None = None


def parse_hh_mm(val: str | None, default: time) -> time:
    if not val:
        return default
    try:
        parts = val.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return default


def calculate_quiet_hours_window(
    now_utc: datetime,
    start_str: str | None,
    end_str: str | None,
    tz_name: str,
) -> tuple[bool, datetime | None]:
    """Deterministically determine whether now_utc falls in quiet hours.

    Handles overnight windows (e.g. 22:00 -> 07:00) using timezone-aware calculations.
    Returns (in_quiet_hours, next_eligible_at_utc).
    """
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("Asia/Dhaka")

    local_dt = now_utc.astimezone(tz)
    current_time = local_dt.time()

    start_time = parse_hh_mm(start_str, time(22, 0))
    end_time = parse_hh_mm(end_str, time(7, 0))

    if start_time == end_time:
        # 0-length window means quiet hours are effectively inactive
        return False, None

    is_overnight = start_time > end_time

    if not is_overnight:
        # Daytime window (e.g. 13:00 -> 14:00)
        in_quiet_hours = start_time <= current_time < end_time
        if in_quiet_hours:
            next_eligible_local = datetime.combine(local_dt.date(), end_time, tzinfo=tz)
            return True, next_eligible_local.astimezone(timezone.utc)
        return False, None
    else:
        # Overnight window (e.g. 22:00 -> 07:00)
        in_quiet_hours = current_time >= start_time or current_time < end_time
        if in_quiet_hours:
            if current_time >= start_time:
                # Before midnight: end time is tomorrow
                next_eligible_local = datetime.combine(
                    local_dt.date() + timedelta(days=1),
                    end_time,
                    tzinfo=tz,
                )
            else:
                # After midnight: end time is today
                next_eligible_local = datetime.combine(
                    local_dt.date(),
                    end_time,
                    tzinfo=tz,
                )
            return True, next_eligible_local.astimezone(timezone.utc)
        return False, None


def evaluate_eligibility(
    preference: NotificationPreference,
    *,
    channel: str,
    alert_severity: str,
    notification_event: str,
    now_utc: datetime | None = None,
    already_sent: bool = False,
) -> EligibilityResult:
    """Evaluate whether a notification should be delivered to the specified channel.

    Channel must be 'in_app' or 'email'.
    Policy:
    - Already sent events are suppressed (idempotency safeguard).
    - Frequency 'off' suppresses the channel.
    - Frequency 'daily_digest' defers immediate delivery.
    - Channel disabled suppresses delivery.
    - Email requires explicit consent.
    - Severity below threshold suppresses delivery.
    - Quiet hours defer non-critical notifications; CRITICAL notifications bypass quiet hours.
    """
    now = now_utc or datetime.now(timezone.utc)
    channel_norm = channel.lower()
    severity_norm = alert_severity.lower()

    if already_sent:
        return EligibilityResult(
            is_eligible=False,
            reason=EligibilityReason.ALREADY_DELIVERED,
        )

    # 1. Frequency policy
    freq = (preference.frequency_mode or "immediate").lower()
    if freq == "off":
        return EligibilityResult(
            is_eligible=False,
            reason=EligibilityReason.FREQUENCY_SUPPRESSED,
        )
    if freq == "daily_digest":
        # Deferred for digest engine; immediate dispatch is suppressed
        return EligibilityResult(
            is_eligible=False,
            reason=EligibilityReason.FREQUENCY_SUPPRESSED,
        )

    # 2. Channel enable and consent checks
    if channel_norm == "in_app":
        if not preference.in_app_enabled:
            return EligibilityResult(
                is_eligible=False,
                reason=EligibilityReason.DISABLED,
            )
        min_sev = (preference.in_app_min_severity or "info").lower()
    elif channel_norm == "email":
        if not preference.email_consent:
            return EligibilityResult(
                is_eligible=False,
                reason=EligibilityReason.NO_CONSENT,
            )
        if not preference.email_enabled:
            return EligibilityResult(
                is_eligible=False,
                reason=EligibilityReason.DISABLED,
            )
        min_sev = (preference.email_min_severity or "warning").lower()
    else:
        return EligibilityResult(
            is_eligible=False,
            reason=EligibilityReason.DISABLED,
        )

    # 3. Severity threshold comparison
    alert_rank = SEVERITY_ORDER.get(severity_norm, 10)
    min_rank = SEVERITY_ORDER.get(min_sev, 10)
    if alert_rank < min_rank:
        return EligibilityResult(
            is_eligible=False,
            reason=EligibilityReason.BELOW_SEVERITY_THRESHOLD,
        )

    # 4. Quiet hours policy
    # Policy: INFO and WARNING (low, medium, warning, high) respect quiet hours.
    # CRITICAL alerts bypass quiet hours to guarantee user safety.
    if preference.quiet_hours_enabled:
        is_critical = severity_norm == "critical"
        if not is_critical:
            in_quiet, next_eligible = calculate_quiet_hours_window(
                now,
                preference.quiet_hours_start,
                preference.quiet_hours_end,
                preference.timezone,
            )
            if in_quiet:
                return EligibilityResult(
                    is_eligible=False,
                    reason=EligibilityReason.QUIET_HOURS,
                    next_eligible_at=next_eligible,
                )

    return EligibilityResult(
        is_eligible=True,
        reason=EligibilityReason.ELIGIBLE,
    )
