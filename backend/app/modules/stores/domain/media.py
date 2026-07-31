from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class StoreMediaType(StrEnum):
    LOGO = "logo"
    BANNER = "banner"
    GALLERY = "gallery"


class StoreMediaStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class StoreMedia:
    id: UUID
    store_id: UUID
    uploaded_by_id: UUID
    media_type: StoreMediaType
    status: StoreMediaStatus
    original_filename: str
    stored_filename: str
    extension: str
    mime_type: str
    file_size: int
    width: int
    height: int
    orientation: int
    aspect_ratio: Decimal
    checksum_sha256: str
    bucket: str
    object_key: str
    etag: str
    display_order: int
    is_public: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    version: int
