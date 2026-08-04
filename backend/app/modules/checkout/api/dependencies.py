from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.cart.api.dependencies import build_cart_service
from app.modules.checkout.application.services import (
    CheckoutOutboxService,
    CheckoutService,
)
from app.modules.checkout.infrastructure.repositories import (
    SqlAlchemyCheckoutItemRepository,
    SqlAlchemyCheckoutOutboxRepository,
    SqlAlchemyCheckoutRepository,
)
from app.modules.inventory.application.services import InventoryService
from app.modules.inventory.infrastructure.repositories import (
    SqlAlchemyInventoryRepository,
)
from app.modules.pricing.application.price_list_services import PricingResolver
from app.modules.pricing.infrastructure.price_list_repositories import (
    SqlAlchemyResolverRepository,
)


async def checkout_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[CheckoutService]:
    service = build_checkout_service(request, session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def build_checkout_service(request: Request, session: AsyncSession) -> CheckoutService:
    events = cast(EventPublisher, request.app.state.store_events)
    return CheckoutService(
        SqlAlchemyCheckoutRepository(session),
        SqlAlchemyCheckoutItemRepository(session),
        build_cart_service(request, session),
        PricingResolver(SqlAlchemyResolverRepository(session), events),
        InventoryService(SqlAlchemyInventoryRepository(session), events),
        CheckoutOutboxService(SqlAlchemyCheckoutOutboxRepository(session)),
    )


CheckoutServiceDependency = Annotated[
    CheckoutService, Depends(checkout_service_dependency)
]
