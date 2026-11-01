"""Typed schemas for user notification preferences."""
from datetime import datetime
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator

SeverityLevel = Literal["critical", "high", "medium", "low", "info", "warning"]
FrequencyMode = Literal["immediate", "daily_digest", "off"]

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class NotificationPreferenceBase(BaseModel):
    in_app_enabled: bool = True
    in_app_min_severity: SeverityLevel = "info"
    email_enabled: bool = False
    email_consent: bool = False
    email_min_severity: SeverityLevel = "warning"
    quiet_hours_enabled: bool = False
    quiet_hours_start: str | None = Field(default="22:00")
    quiet_hours_end: str | None = Field(default="07:00")
    timezone: str = "Asia/Dhaka"
    frequency_mode: FrequencyMode = "immediate"

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def validate_time_format(cls, v: str | None) -> str | None:
        if v is not None and not TIME_PATTERN.match(v):
            raise ValueError("Time must be in 24-hour HH:MM format (e.g. 22:00)")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as err:
            raise ValueError(f"Invalid timezone identifier: {v}") from err
        return v


class NotificationPreferenceUpdate(BaseModel):
    in_app_enabled: bool | None = None
    in_app_min_severity: SeverityLevel | None = None
    email_enabled: bool | None = None
    email_consent: bool | None = None
    email_min_severity: SeverityLevel | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str | None = None
    frequency_mode: FrequencyMode | None = None

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def validate_time_format(cls, v: str | None) -> str | None:
        if v is not None and not TIME_PATTERN.match(v):
            raise ValueError("Time must be in 24-hour HH:MM format (e.g. 22:00)")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError) as err:
                raise ValueError(f"Invalid timezone identifier: {v}") from err
        return v


class NotificationPreferenceResponse(NotificationPreferenceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    email_consent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
