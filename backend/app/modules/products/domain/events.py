from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductEvent:
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
            "product_id": str(self.product_id),
            "catalog_id": str(self.catalog_id),
            "store_id": str(self.store_id),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductCreated(ProductEvent):
    event_name: ClassVar[str] = "product.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductUpdated(ProductEvent):
    event_name: ClassVar[str] = "product.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductArchived(ProductEvent):
    event_name: ClassVar[str] = "product.archived"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductDeleted(ProductEvent):
    event_name: ClassVar[str] = "product.deleted"
