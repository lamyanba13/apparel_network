from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from uuid import UUID


class OpenState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class OperatingInterval:
    opening_time: time
    closing_time: time


@dataclass(frozen=True, slots=True)
class StoreOperatingHours:
    id: UUID
    store_id: UUID
    day_of_week: int
    timezone: str
    opening_time: time | None
    closing_time: time | None
    is_closed: bool
    is_24_hours: bool
    effective_from: datetime | None
    effective_until: datetime | None
    priority: int
    notes: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    version: int

    @property
    def interval(self) -> OperatingInterval | None:
        if self.opening_time is None or self.closing_time is None:
            return None
        return OperatingInterval(self.opening_time, self.closing_time)

    @property
    def is_temporary(self) -> bool:
        return self.effective_from is not None


@dataclass(frozen=True, slots=True)
class StoreSchedule:
    store_id: UUID
    day_of_week: int
    timezone: str
    priority: int
    intervals: tuple[StoreOperatingHours, ...]
    is_temporary_override: bool


@dataclass(frozen=True, slots=True)
class BusinessStatus:
    store_id: UUID
    timezone: str
    current_status: OpenState
    open_now: bool
    is_24_hours: bool
    current_interval: OperatingInterval | None
    today_schedule: StoreSchedule | None
    next_opening: datetime | None
    next_closing: datetime | None
    temporary_override: bool
