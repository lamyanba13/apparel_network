from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogImportEvent:
    catalog_import_id: UUID
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
            "catalog_import_id": str(self.catalog_import_id),
            "store_id": str(self.store_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogImportCreated(CatalogImportEvent):
    event_name: ClassVar[str] = "catalog_import.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogImportValidated(CatalogImportEvent):
    event_name: ClassVar[str] = "catalog_import.validated"


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogImportCompleted(CatalogImportEvent):
    event_name: ClassVar[str] = "catalog_import.completed"


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogImportFailed(CatalogImportEvent):
    event_name: ClassVar[str] = "catalog_import.failed"
