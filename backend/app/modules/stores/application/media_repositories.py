from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.modules.stores.domain import StoreMedia, StoreMediaType


class StoreMediaConstraintError(RuntimeError):
    """Concurrent uniqueness or integrity conflict in Store media."""


class StoreMediaRepository(Protocol):
    async def add(
        self,
        *,
        store_id: UUID,
        uploaded_by_id: UUID,
        media_type: StoreMediaType,
        original_filename: str,
        stored_filename: str,
        extension: str,
        mime_type: str,
        file_size: int,
        width: int,
        height: int,
        orientation: int,
        aspect_ratio: Decimal,
        checksum_sha256: str,
        bucket: str,
        object_key: str,
        etag: str,
        display_order: int,
        is_public: bool,
    ) -> StoreMedia: ...

    async def get(
        self,
        store_id: UUID,
        media_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> StoreMedia | None: ...

    async def list_for_store(
        self,
        store_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[StoreMedia], int]: ...

    async def find_duplicate(
        self,
        store_id: UUID,
        checksum_sha256: str,
    ) -> StoreMedia | None: ...

    async def archive_active(
        self,
        store_id: UUID,
        media_type: StoreMediaType,
    ) -> int: ...

    async def update(
        self,
        store_id: UUID,
        media_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> StoreMedia | None: ...

    async def soft_delete(
        self,
        store_id: UUID,
        media_id: UUID,
        *,
        deleted_at: datetime,
        expected_version: int,
    ) -> StoreMedia | None: ...

    async def count_active(self) -> int: ...
