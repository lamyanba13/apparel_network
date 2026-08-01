from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class TaxonomyEvent:
    entity_id: UUID
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
            "id": str(self.entity_id),
            "store_id": str(self.store_id),
            "version": self.version,
        }


class CategoryCreated(TaxonomyEvent):
    event_name: ClassVar[str] = "category.created"


class CategoryUpdated(TaxonomyEvent):
    event_name: ClassVar[str] = "category.updated"


class CategoryDeleted(TaxonomyEvent):
    event_name: ClassVar[str] = "category.deleted"


class CategoryArchived(TaxonomyEvent):
    event_name: ClassVar[str] = "category.archived"


class CollectionCreated(TaxonomyEvent):
    event_name: ClassVar[str] = "collection.created"


class CollectionUpdated(TaxonomyEvent):
    event_name: ClassVar[str] = "collection.updated"


class CollectionDeleted(TaxonomyEvent):
    event_name: ClassVar[str] = "collection.deleted"


class CollectionArchived(TaxonomyEvent):
    event_name: ClassVar[str] = "collection.archived"


class ProductAssignedToCategory(TaxonomyEvent):
    event_name: ClassVar[str] = "product.category.assigned"


class ProductRemovedFromCategory(TaxonomyEvent):
    event_name: ClassVar[str] = "product.category.removed"


class ProductAssignedToCollection(TaxonomyEvent):
    event_name: ClassVar[str] = "product.collection.assigned"


class ProductRemovedFromCollection(TaxonomyEvent):
    event_name: ClassVar[str] = "product.collection.removed"


class CollectionReordered(TaxonomyEvent):
    event_name: ClassVar[str] = "collection.reordered"
