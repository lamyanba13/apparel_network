from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.modules.notifications.domain import NotificationChannel


@dataclass(frozen=True, slots=True)
class NotificationFilter:
    status: str | None = None
    channel: NotificationChannel | None = None
    unread_only: bool = False
    offset: int = 0
    limit: int = 25


@dataclass(frozen=True, slots=True)
class PreferenceUpdate:
    values: dict[str, object]
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class TestNotification:
    channel: NotificationChannel
    subject: str
    body: str
    actor_id: UUID
