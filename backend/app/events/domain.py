from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.products.domain import OutboxStatus


@dataclass(frozen=True, slots=True)
class ClaimedEvent:
    id: UUID
    event_name: str
    payload: dict[str, object]
    attempts: int
    recovered: bool


@dataclass(frozen=True, slots=True)
class OutboxInspection:
    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_name: str
    occurred_at: datetime
    status: OutboxStatus
    available_at: datetime
    attempts: int
    locked_at: datetime | None
    locked_by: str | None
    dispatched_at: datetime | None
    published_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
