from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class VariantEvent:
    aggregate_id: UUID
    store_id: UUID
    product_id: UUID
    variant_id: UUID
    version: int
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None
    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "aggregate_id": str(self.aggregate_id),
            "store_id": str(self.store_id),
            "product_id": str(self.product_id),
            "variant_id": str(self.variant_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class VariantCreated(VariantEvent):
    event_name: ClassVar[str] = "product_variant.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class VariantUpdated(VariantEvent):
    event_name: ClassVar[str] = "product_variant.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class VariantDeleted(VariantEvent):
    event_name: ClassVar[str] = "product_variant.deleted"


@dataclass(frozen=True, slots=True, kw_only=True)
class VariantAttributeAssigned(VariantEvent):
    event_name: ClassVar[str] = "product_variant.attribute_assigned"


@dataclass(frozen=True, slots=True, kw_only=True)
class VariantAttributeRemoved(VariantEvent):
    event_name: ClassVar[str] = "product_variant.attribute_removed"


@dataclass(frozen=True, slots=True, kw_only=True)
class VariantArchived(VariantEvent):
    event_name: ClassVar[str] = "product_variant.archived"
