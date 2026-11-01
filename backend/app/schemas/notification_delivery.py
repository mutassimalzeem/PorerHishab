"""Notification readiness contract for future delivery channels.

This module defines typed schemas for notification dispatch and delivery tracking
across multiple delivery channels (in-app, web push, email, SMS, WhatsApp) without
coupling to external providers or requiring background workers at this stage.
"""
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

NotificationChannel = Literal["in_app", "web_push", "email", "sms", "whatsapp"]
DeliveryStatus = Literal["pending", "delivered", "failed", "suppressed"]
DeliveryFailureCategory = Literal[
    "invalid_recipient",
    "rate_limited",
    "provider_error",
    "channel_disabled",
    "frequency_capped",
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
