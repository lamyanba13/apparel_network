from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.modules.orders.api.dependencies import build_order_service
from app.modules.payments.application.services import (
    PaymentOutboxService,
    PaymentService,
)
from app.modules.payments.infrastructure.gateway import NullPaymentGateway
from app.modules.payments.infrastructure.repositories import (
    SqlAlchemyPaymentOutboxRepository,
    SqlAlchemyPaymentRepository,
    SqlAlchemyPaymentTransactionRepository,
)


async def payment_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[PaymentService]:
    service = PaymentService(
        SqlAlchemyPaymentRepository(session),
        SqlAlchemyPaymentTransactionRepository(session),
        build_order_service(request, session),
        NullPaymentGateway(),
        PaymentOutboxService(SqlAlchemyPaymentOutboxRepository(session)),
    )
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


PaymentServiceDependency = Annotated[
    PaymentService, Depends(payment_service_dependency)
]
