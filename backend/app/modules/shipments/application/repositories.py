from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.shipments.application.schemas import ShipmentFilter
from app.modules.shipments.domain import (
    Shipment,
    ShipmentEvent,
    ShipmentPackage,
    ShipmentStatus,
    ShipmentTrackingEvent,
)


class ShipmentRepository(Protocol):
    async def add(self, values: Mapping[str, object]) -> Shipment: ...
    async def get_for_order(self, order_id: UUID) -> Shipment | None: ...
    async def get_for_customer(
        self, shipment_id: UUID, customer_id: UUID
    ) -> Shipment | None: ...
    async def list_for_customer(
        self, customer_id: UUID, filters: ShipmentFilter
    ) -> tuple[Sequence[Shipment], int]: ...
    async def transition(
        self,
        shipment_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: ShipmentStatus,
        actor_id: UUID,
        transitioned_at: datetime,
        values: Mapping[str, object] | None = None,
        archive: bool = False,
    ) -> Shipment | None: ...


class ShipmentPackageRepository(Protocol):
    async def add_many(
        self, values: Sequence[Mapping[str, object]]
    ) -> Sequence[ShipmentPackage]: ...
    async def list_for_shipment(
        self, shipment_id: UUID
    ) -> Sequence[ShipmentPackage]: ...


class ShipmentTrackingRepository(Protocol):
    async def add(
        self,
        shipment_id: UUID,
        status: ShipmentStatus,
        description: str,
        occurred_at: datetime,
        location: str | None = None,
    ) -> ShipmentTrackingEvent: ...
    async def list_for_shipment(
        self, shipment_id: UUID
    ) -> Sequence[ShipmentTrackingEvent]: ...


class ShipmentOutboxRepository(Protocol):
    async def add(self, event: ShipmentEvent) -> None: ...
