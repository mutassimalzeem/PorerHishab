"""Pydantic schemas for proactive financial alerts."""
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

AlertSeverity = Literal["critical", "high", "medium", "low", "info"]
AlertStatus = Literal["active", "resolved", "dismissed"]


class FinancialAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    alert_key: str
    alert_type: str
    severity: AlertSeverity
    title: str
    title_key: str
    message: str
    message_key: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str
    action_url: str | None = None
    status: AlertStatus
    is_read: bool = False
    first_detected_at: datetime
    last_detected_at: datetime
    resolved_at: datetime | None = None
    read_at: datetime | None = None
    dismissed_at: datetime | None = None
    actioned_at: datetime | None = None
    occurrence_count: int = 1
    created_at: datetime
    updated_at: datetime


class AlertEvaluationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    created: int
    updated: int
    resolved: int
    unchanged: int
    evaluated_at: datetime


class AlertUnreadCountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unread_count: int


class AlertListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[FinancialAlertResponse]
    total: int
    limit: int
    offset: int
