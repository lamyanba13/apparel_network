from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.reservations.domain import ReservationStatus


@dataclass(frozen=True, slots=True)
class ReservationCreate:
    order_id: UUID
    payment_id: UUID
    actor_id: UUID
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ReservationTransition:
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ReservationFilter:
    store_id: UUID | None = None
    order_id: UUID | None = None
    status: ReservationStatus | None = None
    offset: int = 0
    limit: int = 25
