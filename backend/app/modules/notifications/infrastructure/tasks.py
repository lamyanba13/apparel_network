from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.modules.notifications.application.dispatchers import NotificationDispatcher
from app.modules.notifications.gateways import NullNotificationGateway
from app.modules.notifications.infrastructure.repositories import (
    SqlAlchemyDeliveryRepository,
    SqlAlchemyNotificationOutboxRepository,
    SqlAlchemyNotificationRepository,
    SqlAlchemyPreferenceRepository,
    SqlAlchemyTemplateRepository,
)
from app.worker import celery_app


@celery_app.task(  # type: ignore[untyped-decorator]
    name="notifications.dispatch",
    acks_late=True,
    reject_on_worker_lost=True,
)
def dispatch_notifications() -> int:
    return asyncio.run(_dispatch())


async def _dispatch() -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            dispatcher = NotificationDispatcher(
                SqlAlchemyNotificationRepository(session),
                SqlAlchemyPreferenceRepository(session),
                SqlAlchemyTemplateRepository(session),
                SqlAlchemyDeliveryRepository(session),
                SqlAlchemyNotificationOutboxRepository(
                    session,
                    lease_seconds=settings.outbox_lease_seconds,
                    max_attempts=settings.outbox_max_attempts,
                    retry_base_seconds=settings.outbox_retry_base_seconds,
                ),
                NullNotificationGateway(),
                max_retries=settings.notification_max_retries,
                retry_base_seconds=settings.notification_retry_base_seconds,
            )
            try:
                count = await dispatcher.dispatch_pending(
                    limit=settings.outbox_claim_limit
                )
                await session.commit()
                return count
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()
