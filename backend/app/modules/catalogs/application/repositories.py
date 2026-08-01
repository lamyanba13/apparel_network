from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.catalogs.domain import Catalog, CatalogStatus


class CatalogRepository(Protocol):
    async def store_owned(self, store_id: UUID, owner_id: UUID) -> bool: ...

    async def add(self, values: Mapping[str, object]) -> Catalog: ...

    async def list_for_owner(
        self, owner_id: UUID, *, offset: int, limit: int
    ) -> tuple[Sequence[Catalog], int]: ...

    async def get_for_owner(
        self, catalog_id: UUID, owner_id: UUID
    ) -> Catalog | None: ...

    async def slug_exists(
        self, store_id: UUID, slug: str, *, exclude_id: UUID | None = None
    ) -> bool: ...

    async def update(
        self,
        catalog_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> Catalog | None: ...

    async def archive(
        self,
        catalog_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime | None = None,
    ) -> Catalog | None: ...

    async def transition(
        self,
        catalog_id: UUID,
        owner_id: UUID,
        *,
        status: CatalogStatus,
        expected_version: int,
    ) -> Catalog | None: ...
