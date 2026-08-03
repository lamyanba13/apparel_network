from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.common.events import DomainEvent
from app.common.exceptions import AppError
from app.modules.inventory.application.schemas import InventoryCreate, InventoryUpdate
from app.modules.inventory.application.services import InventoryService
from app.modules.inventory.domain import InventoryItem, InventoryStatus, TrackingPolicy

STORE, CATALOG, PRODUCT, VARIANT, OWNER, INVENTORY = (
    UUID(int=value) for value in range(1, 7)
)
NOW = datetime.now(UTC)


def item(version: int = 1) -> InventoryItem:
    return InventoryItem(
        INVENTORY,
        VARIANT,
        PRODUCT,
        CATALOG,
        STORE,
        "REF-M",
        5,
        1,
        4,
        InventoryStatus.ACTIVE,
        TrackingPolicy.TRACK,
        1,
        NOW,
        NOW,
        None,
        version,
        OWNER,
        OWNER,
    )


class Events:
    def __init__(self) -> None:
        self.values: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.values.append(event)


class Repository:
    async def variant_context(
        self, variant_id: UUID, owner_id: UUID
    ) -> dict[str, object] | None:
        return (
            {
                "product_id": PRODUCT,
                "catalog_id": CATALOG,
                "store_id": STORE,
                "reference": "REF-M",
            }
            if variant_id == VARIANT and owner_id == OWNER
            else None
        )

    async def variant_has_inventory(self, variant_id: UUID) -> bool:
        return False

    async def add(self, values: dict[str, object]) -> InventoryItem:
        return item()

    async def list_for_owner(
        self, owner_id: UUID, **filters: object
    ) -> tuple[list[InventoryItem], int]:
        return [item()], 1

    async def get_for_owner(
        self, inventory_id: UUID, owner_id: UUID
    ) -> InventoryItem | None:
        return item() if inventory_id == INVENTORY and owner_id == OWNER else None

    async def update(
        self,
        inventory_id: UUID,
        owner_id: UUID,
        *,
        values: dict[str, object],
        expected_version: int,
    ) -> InventoryItem | None:
        return item() if expected_version == 1 else None

    async def archive(
        self,
        inventory_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
    ) -> InventoryItem | None:
        return item() if expected_version == 1 else None


@pytest.mark.asyncio
async def test_crud_emits_safe_events_and_derives_available() -> None:
    events, service = Events(), InventoryService(Repository(), Events())
    service = InventoryService(Repository(), events)
    await service.create(
        InventoryCreate(
            VARIANT, 5, 1, InventoryStatus.ACTIVE, TrackingPolicy.TRACK, 1, OWNER
        )
    )
    await service.update_owned(
        INVENTORY, OWNER, InventoryUpdate({"quantity_on_hand": 6}, 1, OWNER)
    )
    await service.delete_owned(INVENTORY, OWNER, 1)
    assert [value.event_name for value in events.values] == [
        "inventory.created",
        "inventory.updated",
        "inventory.adjusted",
        "inventory.deleted",
    ]
    assert events.values[0].payload == {
        "inventory_id": str(INVENTORY),
        "variant_id": str(VARIANT),
        "product_id": str(PRODUCT),
        "catalog_id": str(CATALOG),
        "store_id": str(STORE),
        "version": 1,
    }


@pytest.mark.asyncio
async def test_rejects_cross_store_and_invalid_quantities() -> None:
    service = InventoryService(Repository(), Events())
    with pytest.raises(AppError):
        await service.create(
            InventoryCreate(
                VARIANT, 1, 2, InventoryStatus.ACTIVE, TrackingPolicy.TRACK, 0, OWNER
            )
        )
    with pytest.raises(AppError):
        await service.create(
            InventoryCreate(
                VARIANT,
                1,
                0,
                InventoryStatus.ACTIVE,
                TrackingPolicy.TRACK,
                0,
                UUID(int=99),
            )
        )
    with pytest.raises(AppError):
        await service.update_owned(
            INVENTORY, OWNER, InventoryUpdate({"quantity_reserved": 6}, 1, OWNER)
        )
