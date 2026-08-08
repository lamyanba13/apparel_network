from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationEvent:
    notification_id: UUID
    customer_id: UUID
    store_id: UUID | None
    version: int
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_name: ClassVar[str]

    @property
    def payload(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "notification_id": str(self.notification_id),
            "customer_id": str(self.customer_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }
        if self.store_id is not None:
            payload["store_id"] = str(self.store_id)
        return payload


class NotificationCreated(NotificationEvent):
    event_name = "notification.created"


class NotificationSent(NotificationEvent):
    event_name = "notification.sent"


class NotificationFailed(NotificationEvent):
    event_name = "notification.failed"


class NotificationRead(NotificationEvent):
    event_name = "notification.read"
