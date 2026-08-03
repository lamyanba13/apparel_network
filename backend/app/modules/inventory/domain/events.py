from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class InventoryEvent:
    inventory_id: UUID
    variant_id: UUID
    product_id: UUID
    catalog_id: UUID
    store_id: UUID
    version: int
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None
    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "inventory_id": str(self.inventory_id),
            "variant_id": str(self.variant_id),
            "product_id": str(self.product_id),
            "catalog_id": str(self.catalog_id),
            "store_id": str(self.store_id),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class InventoryCreated(InventoryEvent):
    event_name: ClassVar[str] = "inventory.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class InventoryUpdated(InventoryEvent):
    event_name: ClassVar[str] = "inventory.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class InventoryDeleted(InventoryEvent):
    event_name: ClassVar[str] = "inventory.deleted"


@dataclass(frozen=True, slots=True, kw_only=True)
class InventoryAdjusted(InventoryEvent):
    event_name: ClassVar[str] = "inventory.adjusted"
