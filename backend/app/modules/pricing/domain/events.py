from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductPriceEvent:
    price_id: UUID
    product_id: UUID
    variant_id: UUID | None
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
            "price_id": str(self.price_id),
            "product_id": str(self.product_id),
            "variant_id": str(self.variant_id) if self.variant_id else None,
            "store_id": str(self.store_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductPriceCreated(ProductPriceEvent):
    event_name: ClassVar[str] = "product_price.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductPriceUpdated(ProductPriceEvent):
    event_name: ClassVar[str] = "product_price.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductPriceActivated(ProductPriceEvent):
    event_name: ClassVar[str] = "product_price.activated"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductPriceArchived(ProductPriceEvent):
    event_name: ClassVar[str] = "product_price.archived"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductPriceDeleted(ProductPriceEvent):
    event_name: ClassVar[str] = "product_price.deleted"
