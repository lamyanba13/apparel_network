from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.inventory.application.schemas import (
    InventoryMovementFilter,
    InventoryStockFilter,
    RetailerActivityFilter,
)
from app.modules.inventory.domain import (
    InventoryItem,
    InventoryMovement,
    InventoryStock,
    RetailerOperationsSummary,
    RetailerOrderActivity,
    RetailerShipmentActivity,
)


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
    async def get_locked_for_operator(
        self, inventory_id: UUID, actor_id: UUID
    ) -> InventoryItem | None: ...
    async def active_reservation_quantity(
        self, inventory_id: UUID, now: datetime
    ) -> int: ...
    async def get_for_store(
        self, inventory_id: UUID, store_id: UUID
    ) -> InventoryItem | None: ...
    async def consume(
        self,
        inventory_id: UUID,
        store_id: UUID,
        *,
        quantity: int,
        actor_id: UUID,
        expected_version: int,
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


class InventoryMovementRepository(Protocol):
    async def add(self, values: Mapping[str, object]) -> InventoryMovement: ...
    async def list_for_operator(
        self, actor_id: UUID, filters: InventoryMovementFilter
    ) -> tuple[Sequence[InventoryMovement], int]: ...
    async def list_stock(
        self, actor_id: UUID, filters: InventoryStockFilter, now: datetime
    ) -> tuple[Sequence[InventoryStock], int]: ...


class RetailerOperationsRepository(Protocol):
    async def store_accessible(self, store_id: UUID, actor_id: UUID) -> bool: ...
    async def summary(
        self, store_id: UUID, actor_id: UUID, now: datetime
    ) -> RetailerOperationsSummary | None: ...
    async def list_orders(
        self, actor_id: UUID, filters: RetailerActivityFilter
    ) -> tuple[Sequence[RetailerOrderActivity], int]: ...
    async def list_shipments(
        self, actor_id: UUID, filters: RetailerActivityFilter
    ) -> tuple[Sequence[RetailerShipmentActivity], int]: ...
