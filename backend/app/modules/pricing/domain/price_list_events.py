from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class PriceListEvent:
    price_list_id: UUID | None
    price_id: UUID | None
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
            "price_list_id": str(self.price_list_id) if self.price_list_id else None,
            "price_id": str(self.price_id) if self.price_id else None,
            "store_id": str(self.store_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PriceListCreated(PriceListEvent):
    event_name: ClassVar[str] = "price_list.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class PriceListUpdated(PriceListEvent):
    event_name: ClassVar[str] = "price_list.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class PriceListArchived(PriceListEvent):
    event_name: ClassVar[str] = "price_list.archived"


@dataclass(frozen=True, slots=True, kw_only=True)
class PriceAssigned(PriceListEvent):
    event_name: ClassVar[str] = "price_list.price_assigned"


@dataclass(frozen=True, slots=True, kw_only=True)
class PriceUnassigned(PriceListEvent):
    event_name: ClassVar[str] = "price_list.price_unassigned"


@dataclass(frozen=True, slots=True, kw_only=True)
class PriceResolved(PriceListEvent):
    event_name: ClassVar[str] = "pricing.price_resolved"
