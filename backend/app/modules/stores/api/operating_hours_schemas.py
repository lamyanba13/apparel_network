from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.stores.domain.operating_hours import OpenState


class StoreHoursCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_of_week: int = Field(ge=0, le=6)
    timezone: str = Field(default="Asia/Kolkata", min_length=1, max_length=64)
    opening_time: time | None = None
    closing_time: time | None = None
    is_closed: bool = False
    is_24_hours: bool = False
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    priority: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=500)


class StoreHoursUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    opening_time: time | None = None
    closing_time: time | None = None
    is_closed: bool | None = None
    is_24_hours: bool | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    priority: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=500)


class OperatingIntervalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opening_time: time
    closing_time: time


class StoreHoursResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    version: int


class StoreScheduleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: UUID
    day_of_week: int
    timezone: str
    priority: int
    intervals: list[StoreHoursResponse]
    temporary_override: bool


class StoreHoursListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StoreHoursResponse]


class StoreStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: UUID
    timezone: str
    current_status: OpenState
    open_now: bool
    is_24_hours: bool
    current_interval: OperatingIntervalResponse | None
    today_schedule: StoreScheduleResponse | None
    next_opening: datetime | None
    next_closing: datetime | None
    temporary_override: bool
