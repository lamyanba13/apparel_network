from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreSearchSyncRequested:
    store_id: UUID
    operation: str
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None

    event_name: ClassVar[str] = "store.search.sync.requested"
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "store_id": str(self.store_id),
            "operation": self.operation,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreIndexed:
    store_id: UUID
    operation: str = "index"
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None

    event_name: ClassVar[str] = "store.search.indexed"
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"store_id": str(self.store_id), "operation": self.operation}


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreUpdatedInSearch(StoreIndexed):
    event_name: ClassVar[str] = "store.search.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreRemovedFromSearch(StoreIndexed):
    event_name: ClassVar[str] = "store.search.removed"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreSearchRebuilt(StoreIndexed):
    event_name: ClassVar[str] = "store.search.rebuilt"
