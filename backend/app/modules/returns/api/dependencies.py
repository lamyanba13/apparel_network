from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.modules.inventory.api.dependencies import build_inventory_service
from app.modules.orders.api.dependencies import build_order_service
from app.modules.payments.api.dependencies import build_payment_service
from app.modules.returns.application.services import (
    RefundService,
    ReturnOutboxService,
    ReturnService,
)
from app.modules.returns.infrastructure.gateway import NullRefundGateway
from app.modules.returns.infrastructure.repositories import (
    SqlAlchemyRefundRepository,
    SqlAlchemyRefundTransactionRepository,
    SqlAlchemyReturnItemRepository,
    SqlAlchemyReturnOutboxRepository,
    SqlAlchemyReturnRepository,
)
from app.modules.shipments.api.dependencies import build_shipment_service


def build_return_service(request: Request, session: AsyncSession) -> ReturnService:
    return ReturnService(
        SqlAlchemyReturnRepository(session),
        SqlAlchemyReturnItemRepository(session),
        build_order_service(request, session),
        build_shipment_service(request, session),
        build_payment_service(request, session),
        build_inventory_service(request, session),
        ReturnOutboxService(SqlAlchemyReturnOutboxRepository(session)),
    )


def build_refund_service(request: Request, session: AsyncSession) -> RefundService:
    return RefundService(
        SqlAlchemyRefundRepository(session),
        SqlAlchemyRefundTransactionRepository(session),
        build_return_service(request, session),
        build_payment_service(request, session),
        NullRefundGateway(),
        ReturnOutboxService(SqlAlchemyReturnOutboxRepository(session)),
    )


async def return_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[ReturnService]:
    service = build_return_service(request, session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def refund_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[RefundService]:
    service = build_refund_service(request, session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


ReturnServiceDependency = Annotated[ReturnService, Depends(return_service_dependency)]
RefundServiceDependency = Annotated[RefundService, Depends(refund_service_dependency)]
