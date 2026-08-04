from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.reservations.application.schemas import ReservationFilter
from app.modules.reservations.domain import (
    InventoryReservation,
    ReservationEvent,
    ReservationItem,
    ReservationStatus,
)


class ReservationRepository(Protocol):
    async def get_active_for_order(
        self, order_id: UUID
    ) -> InventoryReservation | None: ...

    async def add(self, values: Mapping[str, object]) -> InventoryReservation: ...

    async def list_for_customer(
        self, customer_id: UUID, filters: ReservationFilter
    ) -> tuple[Sequence[InventoryReservation], int]: ...

    async def get_for_customer(
        self, reservation_id: UUID, customer_id: UUID
    ) -> InventoryReservation | None: ...

    async def transition(
        self,
        reservation_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: ReservationStatus,
        transitioned_at: datetime,
        actor_id: UUID,
        archive: bool = False,
    ) -> InventoryReservation | None: ...


class ReservationItemRepository(Protocol):
    async def active_quantity(self, inventory_item_id: UUID, now: datetime) -> int: ...

    async def add_many(
        self, values: Sequence[Mapping[str, object]]
    ) -> Sequence[ReservationItem]: ...

    async def list_for_reservation(
        self, reservation_id: UUID
    ) -> Sequence[ReservationItem]: ...


class ReservationOutboxRepository(Protocol):
    async def add(self, event: ReservationEvent) -> None: ...
