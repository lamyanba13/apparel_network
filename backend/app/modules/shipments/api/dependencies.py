from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.modules.inventory.api.dependencies import build_inventory_service
from app.modules.orders.api.dependencies import build_order_service
from app.modules.payments.api.dependencies import build_payment_service
from app.modules.reservations.api.dependencies import build_reservation_service
from app.modules.shipments.application.services import (
    ShipmentOutboxService,
    ShipmentService,
)
from app.modules.shipments.infrastructure.gateway import NullShippingGateway
from app.modules.shipments.infrastructure.repositories import (
    SqlAlchemyShipmentOutboxRepository,
    SqlAlchemyShipmentPackageRepository,
    SqlAlchemyShipmentRepository,
    SqlAlchemyShipmentTrackingRepository,
)


async def shipment_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[ShipmentService]:
    service = build_shipment_service(request, session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


def build_shipment_service(request: Request, session: AsyncSession) -> ShipmentService:
    return ShipmentService(
        SqlAlchemyShipmentRepository(session),
        SqlAlchemyShipmentPackageRepository(session),
        SqlAlchemyShipmentTrackingRepository(session),
        build_payment_service(request, session),
        build_order_service(request, session),
        build_reservation_service(request, session),
        build_inventory_service(request, session),
        NullShippingGateway(),
        ShipmentOutboxService(SqlAlchemyShipmentOutboxRepository(session)),
    )


ShipmentServiceDependency = Annotated[
    ShipmentService, Depends(shipment_service_dependency)
]
