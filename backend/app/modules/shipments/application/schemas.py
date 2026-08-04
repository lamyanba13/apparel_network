from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.shipments.domain import ShipmentStatus


@dataclass(frozen=True, slots=True)
class ShipmentCreate:
    order_id: UUID
    reservation_id: UUID
    payment_id: UUID
    shipping_method: str
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class PackageCreate:
    package_number: str
    weight: Decimal
    length: Decimal
    width: Decimal
    height: Decimal


@dataclass(frozen=True, slots=True)
class ShipmentPack:
    expected_version: int
    packages: tuple[PackageCreate, ...]
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ShipmentTransition:
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ShipmentFilter:
    store_id: UUID | None = None
    order_id: UUID | None = None
    status: ShipmentStatus | None = None
    offset: int = 0
    limit: int = 25
