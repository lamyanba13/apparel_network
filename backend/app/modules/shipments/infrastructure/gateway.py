from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from app.modules.shipments.application.gateways import ShippingLabel
from app.modules.shipments.application.schemas import PackageCreate
from app.modules.shipments.domain import ShipmentTrackingEvent


class NullShippingGateway:
    """Deterministic carrier adapter for the provider-neutral foundation."""

    async def create_label(
        self, *, shipment_id: UUID, package: PackageCreate
    ) -> ShippingLabel:
        return ShippingLabel(
            carrier="null-carrier",
            tracking_number=f"NULL-{shipment_id}",
            tracking_url=f"https://shipping.invalid/track/{shipment_id}",
            label_url=f"https://shipping.invalid/labels/{shipment_id}/{package.package_number}",
        )

    async def cancel_label(
        self, *, shipment_id: UUID, tracking_number: str | None
    ) -> None:
        del shipment_id, tracking_number

    async def track(
        self, *, shipment_id: UUID, tracking_number: str
    ) -> tuple[ShipmentTrackingEvent, ...]:
        del shipment_id, tracking_number
        return ()

    async def estimate(
        self, *, shipping_method: str, requested_at: datetime
    ) -> datetime:
        days = 2 if shipping_method == "express" else 5
        return requested_at + timedelta(days=days)

    async def manifest(self, *, shipment_id: UUID) -> str:
        return f"null-manifest-{shipment_id}"
