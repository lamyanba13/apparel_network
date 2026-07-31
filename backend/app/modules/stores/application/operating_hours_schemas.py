from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True, slots=True)
class StoreHoursCreate:
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


@dataclass(frozen=True, slots=True)
class StoreHoursUpdate:
    expected_version: int
    values: dict[str, object]
