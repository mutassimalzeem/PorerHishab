"""Typed schemas for daily notification digests."""
from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict

DigestStatus = Literal["PENDING", "GENERATED", "PROCESSING", "SENT", "FAILED", "SKIPPED"]


class NotificationDigestItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    digest_id: int
    alert_id: int
    severity: str
    alert_type: str
    title: str
    created_at: datetime


class NotificationDigestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    local_date: date
    timezone: str
    status: DigestStatus
    item_count: int
    created_at: datetime
    sent_at: datetime | None = None
    failed_at: datetime | None = None
    failure_reason: str | None = None
    items: list[NotificationDigestItemResponse] = []


class DigestEvaluationResponse(BaseModel):
    status: Literal["generated", "skipped_no_alerts", "already_generated", "skipped_disabled"]
    digest_id: int | None = None
    item_count: int = 0
    local_date: date
    message: str

