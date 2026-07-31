from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.stores.application.services import (
    StoreService,
    StoreSlugService,
    StoreValidationService,
)
from app.modules.stores.infrastructure.persistence.repositories import (
    SqlAlchemyStoreRepository,
)


async def store_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[StoreService]:
    events = cast(EventPublisher, request.app.state.store_events)
    try:
        yield StoreService(
            SqlAlchemyStoreRepository(session),
            events,
            StoreValidationService(),
            StoreSlugService(),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


StoreServiceDependency = Annotated[
    StoreService,
    Depends(store_service_dependency),
]
