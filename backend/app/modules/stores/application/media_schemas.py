from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.stores.domain import StoreMediaStatus, StoreMediaType


@dataclass(frozen=True, slots=True)
class StoreMediaUpload:
    filename: str
    declared_mime_type: str
    data: bytes
    declared_checksum_sha256: str | None = None
    display_order: int = 0
    is_public: bool = False


@dataclass(frozen=True, slots=True)
class ValidatedStoreMedia:
    original_filename: str
    extension: str
    mime_type: str
    data: bytes
    file_size: int
    width: int
    height: int
    orientation: int
    aspect_ratio: Decimal
    checksum_sha256: str
    display_order: int
    is_public: bool


@dataclass(frozen=True, slots=True)
class StoreMediaUpdate:
    expected_version: int
    display_order: int | None = None
    is_public: bool | None = None


@dataclass(frozen=True, slots=True)
class StoreMediaReorderItem:
    media_id: UUID
    display_order: int
    expected_version: int


@dataclass(frozen=True, slots=True)
class StoreMediaPersistence:
    store_id: UUID
    uploaded_by_id: UUID
    media_type: StoreMediaType
    status: StoreMediaStatus
