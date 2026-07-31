from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7

from app.modules.stores.domain.operating_hours import OpenState


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreHoursEvent:
    store_id: UUID
    schedule_id: UUID
    status: OpenState
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None

    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "store_id": str(self.store_id),
            "schedule_id": str(self.schedule_id),
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreHoursCreated(StoreHoursEvent):
    event_name: ClassVar[str] = "store.hours.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreHoursUpdated(StoreHoursEvent):
    event_name: ClassVar[str] = "store.hours.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreHoursDeleted(StoreHoursEvent):
    event_name: ClassVar[str] = "store.hours.deleted"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreOpened(StoreHoursEvent):
    event_name: ClassVar[str] = "store.opened"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreClosed(StoreHoursEvent):
    event_name: ClassVar[str] = "store.closed"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreScheduleActivated(StoreHoursEvent):
    event_name: ClassVar[str] = "store.schedule.activated"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreScheduleExpired(StoreHoursEvent):
    event_name: ClassVar[str] = "store.schedule.expired"
