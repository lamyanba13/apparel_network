from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.cart.application.services import CartOutboxService, CartService
from app.modules.cart.infrastructure.repositories import (
    SqlAlchemyCartOutboxRepository,
    SqlAlchemyShoppingCartItemRepository,
    SqlAlchemyShoppingCartRepository,
)
from app.modules.inventory.application.services import InventoryService
from app.modules.inventory.infrastructure.repositories import (
    SqlAlchemyInventoryRepository,
)
from app.modules.pricing.application.price_list_services import PricingResolver
from app.modules.pricing.infrastructure.price_list_repositories import (
    SqlAlchemyResolverRepository,
)


async def cart_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[CartService]:
    service = build_cart_service(request, session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def build_cart_service(request: Request, session: AsyncSession) -> CartService:
    events = cast(EventPublisher, request.app.state.store_events)
    return CartService(
        SqlAlchemyShoppingCartRepository(session),
        SqlAlchemyShoppingCartItemRepository(session),
        PricingResolver(SqlAlchemyResolverRepository(session), events),
        InventoryService(SqlAlchemyInventoryRepository(session), events),
        CartOutboxService(SqlAlchemyCartOutboxRepository(session)),
    )


CartServiceDependency = Annotated[CartService, Depends(cart_service_dependency)]
