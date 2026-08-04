from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ReservationStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    CONSUMED = "consumed"
    RELEASED = "released"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class InventoryReservation:
    id: UUID
    order_id: UUID
    payment_id: UUID
    customer_id: UUID
    store_id: UUID
    status: ReservationStatus
    expires_at: datetime
    released_at: datetime | None
    consumed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class ReservationItem:
    id: UUID
    reservation_id: UUID
    inventory_item_id: UUID
    variant_id: UUID
    quantity: int
    inventory_version: int
    created_at: datetime
