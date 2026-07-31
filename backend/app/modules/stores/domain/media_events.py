from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7

from app.modules.stores.domain.media import StoreMediaType


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMediaEvent:
    store_id: UUID
    media_id: UUID
    media_type: StoreMediaType
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None

    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "store_id": str(self.store_id),
            "media_id": str(self.media_id),
            "media_type": self.media_type.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreLogoUploaded(StoreMediaEvent):
    event_name: ClassVar[str] = "store.logo.uploaded"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreBannerUploaded(StoreMediaEvent):
    event_name: ClassVar[str] = "store.banner.uploaded"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreGalleryUploaded(StoreMediaEvent):
    event_name: ClassVar[str] = "store.gallery.uploaded"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMediaDeleted(StoreMediaEvent):
    event_name: ClassVar[str] = "store.media.deleted"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMediaReordered(StoreMediaEvent):
    event_name: ClassVar[str] = "store.media.reordered"
