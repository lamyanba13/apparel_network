from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.modules.notifications.application.services import (
    NotificationService,
    NotificationTestService,
)
from app.modules.notifications.gateways import NullNotificationGateway
from app.modules.notifications.infrastructure.repositories import (
    SqlAlchemyDeliveryRepository,
    SqlAlchemyNotificationOutboxRepository,
    SqlAlchemyNotificationRepository,
    SqlAlchemyPreferenceRepository,
    SqlAlchemyTemplateRepository,
)


def build_notification_service(session: AsyncSession) -> NotificationService:
    return NotificationService(
        SqlAlchemyNotificationRepository(session),
        SqlAlchemyPreferenceRepository(session),
        SqlAlchemyTemplateRepository(session),
        SqlAlchemyNotificationOutboxRepository(session),
    )


def build_notification_test_service(session: AsyncSession) -> NotificationTestService:
    return NotificationTestService(
        SqlAlchemyNotificationRepository(session),
        SqlAlchemyTemplateRepository(session),
        SqlAlchemyDeliveryRepository(session),
        SqlAlchemyNotificationOutboxRepository(session),
        NullNotificationGateway(),
    )


async def notification_service_dependency(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[NotificationService]:
    service = build_notification_service(session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def notification_test_service_dependency(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[NotificationTestService]:
    service = build_notification_test_service(session)
    try:
        yield service
        await session.commit()
    except Exception:
        await session.rollback()
        raise


NotificationServiceDependency = Annotated[
    NotificationService, Depends(notification_service_dependency)
]
NotificationTestServiceDependency = Annotated[
    NotificationTestService, Depends(notification_test_service_dependency)
]
