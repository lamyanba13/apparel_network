from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.events import TransactionalOutboxPublisher
from app.modules.inventory.application.services import (
    InventoryService,
    RetailerOperationsService,
)
from app.modules.inventory.infrastructure.repositories import (
    SqlAlchemyInventoryMovementRepository,
    SqlAlchemyInventoryRepository,
    SqlAlchemyRetailerOperationsRepository,
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
    return InventoryService(
        SqlAlchemyInventoryRepository(session),
        TransactionalOutboxPublisher(session, delegate=events),
        SqlAlchemyInventoryMovementRepository(session),
    )


InventoryServiceDependency = Annotated[
    InventoryService, Depends(inventory_service_dependency)
]


async def retailer_operations_dependency(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[RetailerOperationsService]:
    try:
        yield RetailerOperationsService(SqlAlchemyRetailerOperationsRepository(session))
        await session.commit()
    except Exception:
        await session.rollback()
        raise


RetailerOperationsDependency = Annotated[
    RetailerOperationsService, Depends(retailer_operations_dependency)
]
