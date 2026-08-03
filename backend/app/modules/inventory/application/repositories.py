from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.inventory.domain import InventoryItem


class InventoryRepository(Protocol):
    async def variant_context(
        self, variant_id: UUID, owner_id: UUID
    ) -> Mapping[str, object] | None: ...
    async def variant_has_inventory(self, variant_id: UUID) -> bool: ...
    async def add(self, values: Mapping[str, object]) -> InventoryItem: ...
    async def list_for_owner(
        self, owner_id: UUID, **filters: object
    ) -> tuple[Sequence[InventoryItem], int]: ...
    async def get_for_owner(
        self, inventory_id: UUID, owner_id: UUID
    ) -> InventoryItem | None: ...
    async def update(
        self,
        inventory_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> InventoryItem | None: ...
    async def archive(
        self,
        inventory_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
    ) -> InventoryItem | None: ...
