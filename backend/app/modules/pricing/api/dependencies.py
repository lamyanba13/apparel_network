from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.pricing.application.services import PricingService
from app.modules.pricing.infrastructure.repositories import (
    SqlAlchemyProductPriceRepository,
)


async def pricing_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[PricingService]:
    events = cast(EventPublisher, request.app.state.store_events)
    try:
        yield PricingService(SqlAlchemyProductPriceRepository(session), events)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


PricingServiceDependency = Annotated[
    PricingService, Depends(pricing_service_dependency)
]
