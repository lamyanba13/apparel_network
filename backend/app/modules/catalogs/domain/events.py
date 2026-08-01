from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogEvent:
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
            "catalog_id": str(self.catalog_id),
            "store_id": str(self.store_id),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogCreated(CatalogEvent):
    event_name: ClassVar[str] = "catalog.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogUpdated(CatalogEvent):
    event_name: ClassVar[str] = "catalog.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogArchived(CatalogEvent):
    event_name: ClassVar[str] = "catalog.archived"


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogDeleted(CatalogEvent):
    event_name: ClassVar[str] = "catalog.deleted"


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogActivated(CatalogEvent):
    event_name: ClassVar[str] = "catalog.activated"


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogVisibilityChanged(CatalogEvent):
    event_name: ClassVar[str] = "catalog.visibility_changed"
