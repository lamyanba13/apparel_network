from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ProductMediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class ProductMediaRole(StrEnum):
    PRIMARY = "primary"
    GALLERY = "gallery"
    THUMBNAIL = "thumbnail"
    DOCUMENT = "document"


@dataclass(frozen=True, slots=True)
class ProductMedia:
    id: UUID
    product_id: UUID
    store_id: UUID
    catalog_id: UUID
    media_type: ProductMediaType
    role: ProductMediaRole
    storage_provider: str
    bucket: str
    object_key: str
    original_filename: str
    mime_type: str
    extension: str
    file_size: int
    width: int | None
    height: int | None
    duration_seconds: int | None
    checksum_sha256: str
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    version: int
    created_by_id: UUID | None
    updated_by_id: UUID | None
