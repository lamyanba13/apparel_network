from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.inventory.domain import (
    InventoryMovementType,
    InventoryStatus,
    StockClassification,
    TrackingPolicy,
)


@dataclass(frozen=True, slots=True)
class InventoryCreate:
    variant_id: UUID
    quantity_on_hand: int
    quantity_reserved: int
    status: InventoryStatus
    tracking_policy: TrackingPolicy
    low_stock_threshold: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class InventoryUpdate:
    values: Mapping[str, object]
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class InventoryReservationConsumption:
    inventory_id: UUID
    quantity: int


@dataclass(frozen=True, slots=True)
class InventoryAdjustment:
    quantity_delta: int
    movement_type: InventoryMovementType
    reason: str
    expected_version: int
    actor_id: UUID
    source: str = "manual"
    reference_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InventoryReconciliation:
    physical_count: int
    reason: str
    expected_version: int
    actor_id: UUID
    source: str = "physical_count"
    reference_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InventoryMovementFilter:
    store_id: UUID | None
    inventory_id: UUID | None
    variant_id: UUID | None
    movement_type: InventoryMovementType | None
    created_from: datetime | None
    created_to: datetime | None
    actor_id: UUID | None
    source: str | None
    reference_id: UUID | None
    offset: int
    limit: int


@dataclass(frozen=True, slots=True)
class InventoryStockFilter:
    classification: StockClassification
    store_id: UUID | None
    offset: int
    limit: int


@dataclass(frozen=True, slots=True)
class RetailerActivityFilter:
    store_id: UUID
    status: str | None
    offset: int
    limit: int
