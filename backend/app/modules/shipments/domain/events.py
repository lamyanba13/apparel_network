from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class ShipmentEvent:
    shipment_id: UUID
    order_id: UUID
    reservation_id: UUID
    payment_id: UUID
    customer_id: UUID
    store_id: UUID
    version: int
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_name: ClassVar[str]

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "shipment_id": str(self.shipment_id),
            "order_id": str(self.order_id),
            "reservation_id": str(self.reservation_id),
            "payment_id": str(self.payment_id),
            "customer_id": str(self.customer_id),
            "store_id": str(self.store_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ShipmentCreated(ShipmentEvent):
    event_name: ClassVar[str] = "shipment.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class ShipmentPacked(ShipmentEvent):
    event_name: ClassVar[str] = "shipment.packed"


@dataclass(frozen=True, slots=True, kw_only=True)
class ShipmentShipped(ShipmentEvent):
    event_name: ClassVar[str] = "shipment.shipped"


@dataclass(frozen=True, slots=True, kw_only=True)
class ShipmentOutForDelivery(ShipmentEvent):
    event_name: ClassVar[str] = "shipment.out_for_delivery"


@dataclass(frozen=True, slots=True, kw_only=True)
class ShipmentDelivered(ShipmentEvent):
    event_name: ClassVar[str] = "shipment.delivered"


@dataclass(frozen=True, slots=True, kw_only=True)
class ShipmentCancelled(ShipmentEvent):
    event_name: ClassVar[str] = "shipment.cancelled"


@dataclass(frozen=True, slots=True, kw_only=True)
class ShipmentReturnRequested(ShipmentEvent):
    event_name: ClassVar[str] = "shipment.return_requested"


@dataclass(frozen=True, slots=True, kw_only=True)
class ShipmentReturned(ShipmentEvent):
    event_name: ClassVar[str] = "shipment.returned"
