from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.stores.domain import (
    StoreMembership,
    StoreMembershipRole,
    StoreMembershipStatus,
)


class StoreMembershipRepository(Protocol):
    async def add_owner(
        self,
        *,
        store_id: UUID,
        user_id: UUID,
        accepted_at: datetime,
    ) -> StoreMembership: ...

    async def add_invitation(
        self,
        *,
        store_id: UUID,
        user_id: UUID,
        role: StoreMembershipRole,
        invited_by_id: UUID,
        expires_at: datetime,
    ) -> StoreMembership: ...

    async def get(
        self,
        store_id: UUID,
        membership_id: UUID,
    ) -> StoreMembership | None: ...

    async def get_owner(self, store_id: UUID) -> StoreMembership | None: ...

    async def find_open(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> StoreMembership | None: ...

    async def list_for_store(
        self,
        store_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[StoreMembership], int]: ...

    async def transition(
        self,
        membership_id: UUID,
        *,
        from_statuses: frozenset[StoreMembershipStatus],
        status: StoreMembershipStatus,
        expected_version: int,
        accepted_at: datetime | None = None,
        removed_at: datetime | None = None,
    ) -> StoreMembership | None: ...

    async def update_role(
        self,
        membership_id: UUID,
        *,
        role: StoreMembershipRole,
        expected_version: int,
    ) -> StoreMembership | None: ...

    async def expire_pending(self, store_id: UUID, *, now: datetime) -> int: ...

    async def count_current(self) -> int: ...
