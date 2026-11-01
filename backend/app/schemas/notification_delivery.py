"""Notification readiness and delivery schemas for proactive alerts.

This module defines typed schemas for notification dispatch, delivery tracking,
and query contracts across delivery channels (in-app, email).
"""
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

NotificationChannel = Literal["in_app", "web_push", "email", "sms", "whatsapp"]
DeliveryStatus = Literal[
    "PENDING",
    "PROCESSING",
    "SENT",
    "FAILED",
    "DEAD_LETTER",
    "SUPPRESSED",
    "pending",
    "delivered",
    "failed",
    "suppressed",
]
DeliveryFailureCategory = Literal[
    "invalid_recipient",
    "rate_limited",
    "provider_error",
    "channel_disabled",
    "frequency_capped",
    "quiet_hours",
    "below_threshold",
    "no_consent",
    "transient",
    "permanent",
    "none",
]


class NotificationDeliveryEvent(BaseModel):
    """A readiness contract describing a delivery event for a financial alert."""

    model_config = ConfigDict(from_attributes=True)

    alert_id: int
    user_id: int
    event_type: str
    channel: NotificationChannel
    idempotency_key: str
    delivery_status: DeliveryStatus
    created_at: datetime
    attempted_at: datetime | None = None
    delivered_at: datetime | None = None
    failure_category: DeliveryFailureCategory | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationDeliveryResponse(BaseModel):
    """Public authenticated schema for notification delivery status."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    alert_id: int
    channel: str
    notification_event: str
    idempotency_key: str
    status: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None = None
    last_attempt_at: datetime | None = None
    delivered_at: datetime | None = None
    failed_at: datetime | None = None
    provider: str | None = None
    failure_reason: str | None = None
    failure_category: str | None = None
    created_at: datetime
    updated_at: datetime


class NotificationDeliveryListResponse(BaseModel):
    """Paginated list of notification deliveries."""

    model_config = ConfigDict(from_attributes=True)

    items: list[NotificationDeliveryResponse]
    total: int
    limit: int
    offset: int
