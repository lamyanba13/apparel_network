import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import DomainEvent
from app.modules.catalogs.application.schemas import CatalogCreate
from app.modules.catalogs.application.services import CatalogService
from app.modules.catalogs.domain import Catalog, CatalogStatus, CatalogVisibility
from app.modules.catalogs.infrastructure.repositories import (
    SqlAlchemyCatalogRepository,
)
from app.modules.stores.domain import Store
from tests.helpers.builders import catalog_name, slug


class _DiscardingEventPublisher:
    async def publish(self, event: DomainEvent) -> None:
        del event


async def create_catalog(
    session: AsyncSession,
    verified_store: Store,
    value: int = 1,
) -> Catalog:
    service = CatalogService(
        SqlAlchemyCatalogRepository(session),
        _DiscardingEventPublisher(),
    )
    return await service.create(
        CatalogCreate(
            store_id=verified_store.id,
            name=catalog_name(value),
            slug=slug(value, prefix="catalog"),
            description=f"Integration test catalog {value}",
            status=CatalogStatus.DRAFT,
            visibility=CatalogVisibility.PUBLIC,
            sort_order=value,
            actor_id=verified_store.owner_id,
            is_default=False,
        )
    )


@pytest.fixture
async def catalog(db_session: AsyncSession, verified_store: Store) -> Catalog:
    return await create_catalog(db_session, verified_store)
