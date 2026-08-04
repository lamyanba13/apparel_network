from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class ShipmentStatus(StrEnum):
    CREATED = "created"
    READY_FOR_FULFILLMENT = "ready_for_fulfillment"
    PACKED = "packed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURN_REQUESTED = "return_requested"
    RETURNED = "returned"


@dataclass(frozen=True, slots=True)
class Shipment:
    id: UUID
    order_id: UUID
    reservation_id: UUID
    payment_id: UUID
    customer_id: UUID
    store_id: UUID
    status: ShipmentStatus
    carrier: str | None
    tracking_number: str | None
    tracking_url: str | None
    shipping_method: str
    estimated_delivery_at: datetime | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class ShipmentPackage:
    id: UUID
    shipment_id: UUID
    package_number: str
    weight: Decimal
    length: Decimal
    width: Decimal
    height: Decimal
    label_url: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ShipmentTrackingEvent:
    id: UUID
    shipment_id: UUID
    status: ShipmentStatus
    location: str | None
    description: str
    occurred_at: datetime
