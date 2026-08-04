from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.modules.checkout.api.dependencies import build_checkout_service
from app.modules.inventory.api.dependencies import build_inventory_service
from app.modules.orders.api.dependencies import build_order_service
from app.modules.payments.api.dependencies import build_payment_service
from app.modules.reservations.application.services import (
    ReservationOutboxService,
    ReservationService,
)
from app.modules.reservations.infrastructure.repositories import (
    SqlAlchemyReservationItemRepository,
    SqlAlchemyReservationOutboxRepository,
    SqlAlchemyReservationRepository,
)


async def reservation_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[ReservationService]:
    service = build_reservation_service(request, session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def build_reservation_service(
    request: Request, session: AsyncSession
) -> ReservationService:
    return ReservationService(
        SqlAlchemyReservationRepository(session),
        SqlAlchemyReservationItemRepository(session),
        build_payment_service(request, session),
        build_order_service(request, session),
        build_checkout_service(request, session),
        build_inventory_service(request, session),
        ReservationOutboxService(SqlAlchemyReservationOutboxRepository(session)),
    )


ReservationServiceDependency = Annotated[
    ReservationService, Depends(reservation_service_dependency)
]
