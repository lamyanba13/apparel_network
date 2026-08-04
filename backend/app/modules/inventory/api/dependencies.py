from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.inventory.application.services import InventoryService
from app.modules.inventory.infrastructure.repositories import (
    SqlAlchemyInventoryRepository,
)


async def inventory_service_dependency(
    request: Request, session: Annotated[AsyncSession, Depends(get_db)]
) -> AsyncIterator[InventoryService]:
    service = build_inventory_service(request, session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def build_inventory_service(
    request: Request, session: AsyncSession
) -> InventoryService:
    events = cast(EventPublisher, request.app.state.store_events)
    return InventoryService(SqlAlchemyInventoryRepository(session), events)


InventoryServiceDependency = Annotated[
    InventoryService, Depends(inventory_service_dependency)
]
