from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class InventoryStatus(StrEnum):
    ACTIVE = "active"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"


class TrackingPolicy(StrEnum):
    TRACK = "track"
    DO_NOT_TRACK = "do_not_track"
    PREORDER = "preorder"


class InventoryMovementType(StrEnum):
    INITIAL_STOCK = "initial_stock"
    MANUAL_INCREASE = "manual_increase"
    MANUAL_DECREASE = "manual_decrease"
    DAMAGE = "damage"
    LOSS = "loss"
    FOUND = "found"
    CORRECTION = "correction"
    RECONCILIATION = "reconciliation"
    RESERVATION_CONSUMPTION = "reservation_consumption"
    LEGACY_UPDATE = "legacy_update"


class StockClassification(StrEnum):
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    HEALTHY = "healthy"


@dataclass(frozen=True, slots=True)
class InventoryItem:
    id: UUID
    variant_id: UUID
    product_id: UUID
    catalog_id: UUID
    store_id: UUID
    sku_snapshot: str
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int
    status: InventoryStatus
    tracking_policy: TrackingPolicy
    low_stock_threshold: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    version: int
    created_by_id: UUID | None
    updated_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class InventoryMovement:
    id: UUID
    inventory_id: UUID
    store_id: UUID
    variant_id: UUID
    movement_type: InventoryMovementType
    quantity_delta: int
    previous_on_hand: int
    new_on_hand: int
    previous_available: int
    new_available: int
    reservation_quantity: int
    reason: str
    actor_id: UUID
    source: str
    reference_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class InventoryStock:
    inventory: InventoryItem
    active_reservation_quantity: int
    effective_available: int
    classification: StockClassification


@dataclass(frozen=True, slots=True)
class RetailerOrderActivity:
    id: UUID
    store_id: UUID
    order_number: str
    status: str
    placed_at: datetime
    shipment_status: str | None


@dataclass(frozen=True, slots=True)
class RetailerShipmentActivity:
    id: UUID
    store_id: UUID
    order_id: UUID
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RetailerOperationsSummary:
    store_id: UUID
    active_products: int
    active_variants: int
    in_stock_variants: int
    low_stock_variants: int
    out_of_stock_variants: int
    orders_awaiting_fulfillment: int
    orders_requiring_attention: int
    shipments_pending_fulfillment: int
    shipments_in_transit: int
    recent_movements: tuple[InventoryMovement, ...]
