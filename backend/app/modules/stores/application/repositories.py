from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.stores.domain import (
    Store,
    StoreAddress,
    StoreContact,
    StoreStatus,
    VerificationStatus,
)


class StoreRepository(Protocol):
    async def add(
        self,
        *,
        owner_id: UUID,
        name: str,
        slug: str,
        description: str | None,
        contact: StoreContact,
        address: StoreAddress,
        logo_url: str | None,
        banner_url: str | None,
    ) -> Store: ...

    async def slug_exists(self, slug: str) -> bool: ...

    async def list_for_owner(
        self,
        owner_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Store], int]: ...

    async def get_for_owner(self, store_id: UUID, owner_id: UUID) -> Store | None: ...

    async def get_by_id(self, store_id: UUID) -> Store | None: ...

    async def update(
        self,
        store_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> Store | None: ...

    async def transition(
        self,
        store_id: UUID,
        *,
        from_statuses: frozenset[StoreStatus],
        status: StoreStatus,
        verification_status: VerificationStatus | None = None,
        deleted_at: datetime | None = None,
    ) -> Store | None: ...

    async def close_for_owner(
        self,
        store_id: UUID,
        owner_id: UUID,
        *,
        deleted_at: datetime,
    ) -> Store | None: ...

    async def count_active_and_verified(self) -> tuple[int, int]: ...
