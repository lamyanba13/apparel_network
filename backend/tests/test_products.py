from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.common.events import DomainEvent
from app.common.exceptions import AppError
from app.modules.products.application.schemas import ProductCreate, ProductUpdate
from app.modules.products.application.services import (
    ProductService,
    ProductValidationService,
)
from app.modules.products.domain import Product, ProductStatus, ProductVisibility

STORE = UUID(int=1)
CATALOG = UUID(int=2)
OWNER = UUID(int=3)
NOW = datetime.now(UTC)


def product(version: int = 1) -> Product:
    return Product(
        UUID(int=4),
        CATALOG,
        STORE,
        "Linen Shirt",
        "linen-shirt",
        None,
        None,
        ProductStatus.DRAFT,
        ProductVisibility.PUBLIC,
        "LN-001",
        None,
        0,
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
        self.value = product()

    async def catalog_store(self, catalog_id: UUID, owner_id: UUID) -> UUID | None:
        return STORE if catalog_id == CATALOG and owner_id == OWNER else None

    async def add(self, values: Mapping[str, object]) -> Product:
        return self.value

    async def list_for_owner(
        self, owner_id: UUID, **kwargs: object
    ) -> tuple[list[Product], int]:
        return [self.value], 1

    async def get_for_owner(self, product_id: UUID, owner_id: UUID) -> Product | None:
        return self.value if owner_id == OWNER else None

    async def slug_exists(
        self, catalog_id: UUID, slug: str, *, exclude_id: UUID | None = None
    ) -> bool:
        return False

    async def sku_exists(
        self, store_id: UUID, sku: str, *, exclude_id: UUID | None = None
    ) -> bool:
        return False

    async def update(
        self,
        product_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> Product | None:
        return self.value if expected_version == 1 else None

    async def archive(
        self,
        product_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
    ) -> Product | None:
        return self.value if expected_version == 1 else None

    async def transition(
        self,
        product_id: UUID,
        owner_id: UUID,
        *,
        status: ProductStatus,
        expected_version: int,
    ) -> Product | None:
        return self.value if expected_version == 1 else None


def create_values() -> ProductCreate:
    return ProductCreate(
        CATALOG,
        "Linen Shirt",
        "Linen Shirt",
        "Light linen",
        None,
        ProductStatus.DRAFT,
        ProductVisibility.PUBLIC,
        "ln-001",
        None,
        0,
        OWNER,
    )


def test_validation_normalizes_slug_and_sku() -> None:
    value = ProductValidationService().validate_create(create_values())
    assert value.slug == "linen-shirt"
    assert value.sku == "LN-001"
    with pytest.raises(AppError):
        ProductValidationService().slug("!!!")


@pytest.mark.asyncio
async def test_create_checks_catalog_ownership_and_emits_safe_event() -> None:
    events = Events()
    result = await ProductService(Repository(), events).create(create_values())
    assert result.id == UUID(int=4)
    assert events.values[0].payload == {
        "product_id": str(result.id),
        "catalog_id": str(CATALOG),
        "store_id": str(STORE),
        "version": 1,
    }


@pytest.mark.asyncio
async def test_cross_store_catalog_returns_not_found() -> None:
    repository = Repository()
    with pytest.raises(AppError):
        await ProductService(repository, Events()).create(
            ProductCreate(
                CATALOG,
                "Name",
                "name",
                None,
                None,
                ProductStatus.DRAFT,
                ProductVisibility.PUBLIC,
                "SKU",
                None,
                0,
                UUID(int=99),
            )
        )


@pytest.mark.asyncio
async def test_update_delete_and_optimistic_locking() -> None:
    events = Events()
    service = ProductService(Repository(), events)
    await service.update_owned(
        UUID(int=4), OWNER, ProductUpdate({"name": "Updated"}, 1, OWNER)
    )
    await service.delete_owned(UUID(int=4), OWNER, 1)
    assert [event.event_name for event in events.values] == [
        "product.updated",
        "product.deleted",
    ]


def test_product_update_cannot_move_catalog() -> None:
    with pytest.raises(AppError):
        ProductValidationService().validate_changes({"catalog_id": UUID(int=99)})


def test_product_lifecycle_values_are_stable() -> None:
    assert [value.value for value in ProductStatus] == ["draft", "active", "archived"]
    assert [value.value for value in ProductVisibility] == [
        "public",
        "private",
        "hidden",
    ]
