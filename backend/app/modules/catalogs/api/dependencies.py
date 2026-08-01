from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.catalogs.application.services import CatalogService
from app.modules.catalogs.infrastructure.repositories import SqlAlchemyCatalogRepository


async def catalog_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[CatalogService]:
    events = cast(EventPublisher, request.app.state.store_events)
    try:
        yield CatalogService(SqlAlchemyCatalogRepository(session), events)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


CatalogServiceDependency = Annotated[
    CatalogService, Depends(catalog_service_dependency)
]
