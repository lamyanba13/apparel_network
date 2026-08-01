from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.common.events import DomainEvent
from app.common.exceptions import AppError
from app.modules.catalogs.application.schemas import CatalogCreate, CatalogUpdate
from app.modules.catalogs.application.services import (
    CatalogService,
    CatalogValidationService,
)
from app.modules.catalogs.domain import Catalog, CatalogStatus, CatalogVisibility

STORE = UUID(int=1)
OWNER = UUID(int=2)
NOW = datetime.now(UTC)


def catalog(
    *, status: CatalogStatus = CatalogStatus.DRAFT, version: int = 1
) -> Catalog:
    return Catalog(
        UUID(int=3),
        STORE,
        "Summer",
        "summer",
        None,
        status,
        CatalogVisibility.PUBLIC,
        0,
        None,
        None,
        False,
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
    def __init__(self) -> None:
        self.value = catalog()
        self.owned = True
        self.flushes = 0

    async def store_owned(self, store_id: UUID, owner_id: UUID) -> bool:
        return self.owned and store_id == STORE and owner_id == OWNER

    async def slug_exists(
        self, store_id: UUID, slug: str, *, exclude_id: UUID | None = None
    ) -> bool:
        return slug == self.value.slug and exclude_id != self.value.id

    async def add(self, values: dict[str, object]) -> Catalog:
        self.flushes += 1
        return self.value

    async def list_for_owner(
        self, owner_id: UUID, *, offset: int, limit: int
    ) -> tuple[list[Catalog], int]:
        return [self.value], 1

    async def get_for_owner(self, catalog_id: UUID, owner_id: UUID) -> Catalog | None:
        return self.value if catalog_id == self.value.id and owner_id == OWNER else None

    async def update(
        self,
        catalog_id: UUID,
        owner_id: UUID,
        *,
        values: dict[str, object],
        expected_version: int,
    ) -> Catalog | None:
        return self.value if expected_version == self.value.version else None

    async def archive(
        self,
        catalog_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime | None = None,
    ) -> Catalog | None:
        return self.value if expected_version == self.value.version else None

    async def transition(
        self,
        catalog_id: UUID,
        owner_id: UUID,
        *,
        status: CatalogStatus,
        expected_version: int,
    ) -> Catalog | None:
        return self.value if expected_version == self.value.version else None


def create_values() -> CatalogCreate:
    return CatalogCreate(
        STORE,
        "Summer",
        "summer-new",
        "Seasonal",
        CatalogStatus.DRAFT,
        CatalogVisibility.PUBLIC,
        0,
        OWNER,
        False,
    )


def test_validation_normalizes_and_rejects_invalid_values() -> None:
    service = CatalogValidationService()
    assert service.validate_create(create_values()).name == "Summer"
    with pytest.raises(AppError):
        service.slug("admin")


@pytest.mark.asyncio
async def test_create_enforces_store_ownership_and_emits_safe_event() -> None:
    repository = Repository()
    events = Events()
    result = await CatalogService(repository, events).create(create_values())
    assert result.id == UUID(int=3)
    assert repository.flushes == 1
    assert events.values[0].payload == {
        "catalog_id": str(result.id),
        "store_id": str(STORE),
        "version": 1,
    }


@pytest.mark.asyncio
async def test_cross_store_create_is_not_found() -> None:
    repository = Repository()
    repository.owned = False
    with pytest.raises(AppError):
        await CatalogService(repository, Events()).create(create_values())


@pytest.mark.asyncio
async def test_update_and_delete_use_optimistic_version() -> None:
    repository = Repository()
    events = Events()
    service = CatalogService(repository, events)
    await service.update_owned(
        repository.value.id, OWNER, CatalogUpdate({"name": "Updated"}, 1, OWNER)
    )
    await service.delete_owned(repository.value.id, OWNER, 1)
    assert [event.event_name for event in events.values] == [
        "catalog.updated",
        "catalog.deleted",
    ]


def test_catalog_lifecycle_values_are_stable() -> None:
    assert [status.value for status in CatalogStatus] == ["draft", "active", "archived"]
    assert [value.value for value in CatalogVisibility] == [
        "public",
        "private",
        "hidden",
    ]
