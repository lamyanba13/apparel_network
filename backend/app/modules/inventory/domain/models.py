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
