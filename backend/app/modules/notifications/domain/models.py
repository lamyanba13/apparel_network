from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import JsonValue


class NotificationChannel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    SENDING = "sending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class NotificationTemplate:
    id: UUID
    key: str
    event_name: str
    channel: NotificationChannel
    language: str
    subject: str
    body: str
    variables: tuple[str, ...]
    active: bool
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationPreference:
    id: UUID
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

    def channel_enabled(
        self, channel: NotificationChannel, *, transactional: bool
    ) -> bool:
        enabled = {
            NotificationChannel.EMAIL: self.email_enabled,
            NotificationChannel.SMS: self.sms_enabled,
            NotificationChannel.PUSH: self.push_enabled,
            NotificationChannel.IN_APP: self.in_app_enabled,
        }[channel]
        return enabled and (transactional or self.marketing_opt_in)


@dataclass(frozen=True, slots=True)
class Notification:
    id: UUID
    customer_id: UUID
    store_id: UUID | None
    template_id: UUID
    source_event_id: UUID | None
    event_name: str
    channel: NotificationChannel
    status: NotificationStatus
    subject: str
    body: str
    variables: dict[str, JsonValue]
    attempt_count: int
    max_retries: int
    next_retry_at: datetime | None
    queued_at: datetime | None
    sending_at: datetime | None
    delivered_at: datetime | None
    failed_at: datetime | None
    cancelled_at: datetime | None
    read_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True)
class NotificationDelivery:
    id: UUID
    notification_id: UUID
    channel: NotificationChannel
    gateway_reference: str
    duration_ms: int
    delivered_at: datetime
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationFailure:
    id: UUID
    notification_id: UUID
    attempt: int
    error_code: str
    error_detail: str
    retry_at: datetime | None
    occurred_at: datetime
    version: int
    created_at: datetime
    updated_at: datetime
