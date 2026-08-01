from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.products.application.services import ProductService
from app.modules.products.infrastructure.repositories import SqlAlchemyProductRepository


async def product_service_dependency(
    request: Request, session: Annotated[AsyncSession, Depends(get_db)]
) -> AsyncIterator[ProductService]:
    events = cast(EventPublisher, request.app.state.store_events)
    try:
        yield ProductService(SqlAlchemyProductRepository(session), events)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


ProductServiceDependency = Annotated[
    ProductService, Depends(product_service_dependency)
]
