from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.shipments.application.schemas import PackageCreate
from app.modules.shipments.domain import ShipmentTrackingEvent


@dataclass(frozen=True, slots=True)
class ShippingLabel:
    carrier: str
    tracking_number: str
    tracking_url: str
    label_url: str


class ShippingGateway(Protocol):
    async def create_label(
        self, *, shipment_id: UUID, package: PackageCreate
    ) -> ShippingLabel: ...

    async def cancel_label(
        self, *, shipment_id: UUID, tracking_number: str | None
    ) -> None: ...

    async def track(
        self, *, shipment_id: UUID, tracking_number: str
    ) -> tuple[ShipmentTrackingEvent, ...]: ...

    async def estimate(
        self, *, shipping_method: str, requested_at: datetime
    ) -> datetime: ...

    async def manifest(self, *, shipment_id: UUID) -> str: ...
