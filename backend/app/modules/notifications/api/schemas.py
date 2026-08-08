from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.notifications.domain import NotificationChannel, NotificationStatus


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID
    store_id: UUID | None
    event_name: str
    channel: NotificationChannel
    status: NotificationStatus
    subject: str
    body: str
    attempt_count: int
    read_at: datetime | None
    delivered_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    page: PageMetadata


class MarkReadRequest(BaseModel):
    version: int = Field(ge=1)


class PreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    customer_id: UUID
    email_enabled: bool
    sms_enabled: bool
    push_enabled: bool
    in_app_enabled: bool
    language: str
    marketing_opt_in: bool
    version: int
    created_at: datetime
    updated_at: datetime


class PreferenceUpdateRequest(BaseModel):
    email_enabled: bool | None = None
    sms_enabled: bool | None = None
    push_enabled: bool | None = None
    in_app_enabled: bool | None = None
    language: str | None = Field(default=None, min_length=2, max_length=10)
    marketing_opt_in: bool | None = None
    version: int = Field(ge=1)


class TestNotificationRequest(BaseModel):
    channel: NotificationChannel
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=4000)
