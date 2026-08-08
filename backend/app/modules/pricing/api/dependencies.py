from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.events import TransactionalOutboxPublisher
from app.modules.pricing.application.price_list_services import (
    PriceListService,
    PricingResolver,
)
from app.modules.pricing.application.services import PricingService
from app.modules.pricing.infrastructure.price_list_repositories import (
    SqlAlchemyAssignmentRepository,
    SqlAlchemyPriceListRepository,
    SqlAlchemyResolverRepository,
)
from app.modules.pricing.infrastructure.repositories import (
    SqlAlchemyProductPriceRepository,
)


async def pricing_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[PricingService]:
    events = cast(EventPublisher, request.app.state.store_events)
    try:
        yield PricingService(
            SqlAlchemyProductPriceRepository(session),
            TransactionalOutboxPublisher(session, delegate=events),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


PricingServiceDependency = Annotated[
    PricingService, Depends(pricing_service_dependency)
]


async def price_list_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[PriceListService]:
    events = cast(EventPublisher, request.app.state.store_events)
    try:
        yield PriceListService(
            SqlAlchemyPriceListRepository(session),
            SqlAlchemyAssignmentRepository(session),
            TransactionalOutboxPublisher(session, delegate=events),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def pricing_resolver_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[PricingResolver]:
    events = cast(EventPublisher, request.app.state.store_events)
    try:
        yield PricingResolver(
            SqlAlchemyResolverRepository(session),
            TransactionalOutboxPublisher(session, delegate=events),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


PriceListServiceDependency = Annotated[
    PriceListService, Depends(price_list_service_dependency)
]
PricingResolverDependency = Annotated[
    PricingResolver, Depends(pricing_resolver_dependency)
]
