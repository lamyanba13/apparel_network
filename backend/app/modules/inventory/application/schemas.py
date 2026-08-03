from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from app.modules.inventory.domain import InventoryStatus, TrackingPolicy


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
