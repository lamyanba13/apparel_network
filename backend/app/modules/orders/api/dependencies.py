from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.modules.checkout.api.dependencies import build_checkout_service
from app.modules.orders.application.services import (
    OrderNumberService,
    OrderOutboxService,
    OrderService,
)
from app.modules.orders.infrastructure.repositories import (
    SqlAlchemyOrderItemRepository,
    SqlAlchemyOrderOutboxRepository,
    SqlAlchemyOrderRepository,
)


async def order_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[OrderService]:
    service = build_order_service(request, session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def build_order_service(request: Request, session: AsyncSession) -> OrderService:
    orders = SqlAlchemyOrderRepository(session)
    return OrderService(
        orders,
        SqlAlchemyOrderItemRepository(session),
        build_checkout_service(request, session),
        OrderNumberService(orders),
        OrderOutboxService(SqlAlchemyOrderOutboxRepository(session)),
    )


OrderServiceDependency = Annotated[OrderService, Depends(order_service_dependency)]
