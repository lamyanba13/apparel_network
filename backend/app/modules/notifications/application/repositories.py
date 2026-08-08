from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.notifications.application.schemas import NotificationFilter
from app.modules.notifications.domain import (
    Notification,
    NotificationChannel,
    NotificationEvent,
    NotificationPreference,
    NotificationTemplate,
)


class NotificationRepository(Protocol):
    async def add(self, values: Mapping[str, object]) -> Notification: ...
    async def get_for_customer(
        self, notification_id: UUID, customer_id: UUID, *, for_update: bool = False
    ) -> Notification | None: ...
    async def get_by_source(
        self,
        source_event_id: UUID,
        customer_id: UUID,
        channel: NotificationChannel,
        *,
        for_update: bool = False,
    ) -> Notification | None: ...
    async def list_for_customer(
        self, customer_id: UUID, filters: NotificationFilter
    ) -> tuple[Sequence[Notification], int]: ...
    async def transition(
        self, notification_id: UUID, expected_version: int, values: Mapping[str, object]
    ) -> Notification | None: ...


class PreferenceRepository(Protocol):
    async def get(
        self, customer_id: UUID, *, for_update: bool = False
    ) -> NotificationPreference | None: ...
    async def add_default(
        self, customer_id: UUID, actor_id: UUID | None = None
    ) -> NotificationPreference: ...
    async def update(
        self, customer_id: UUID, expected_version: int, values: Mapping[str, object]
    ) -> NotificationPreference | None: ...


class TemplateRepository(Protocol):
    async def get_for_event(
        self, event_name: str, channel: NotificationChannel, language: str
    ) -> NotificationTemplate | None: ...


class DeliveryRepository(Protocol):
    async def exists(self, notification_id: UUID) -> bool: ...
    async def add(self, values: Mapping[str, object]) -> None: ...
    async def add_failure(self, values: Mapping[str, object]) -> None: ...


class NotificationOutboxRepository(Protocol):
    async def pending(
        self, event_names: Sequence[str], limit: int
    ) -> Sequence[tuple[UUID, str, dict[str, object]]]: ...
    async def mark_published(self, event_id: UUID, at: datetime) -> None: ...
    async def add(self, event: NotificationEvent) -> None: ...
