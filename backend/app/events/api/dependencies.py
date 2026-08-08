from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import Settings
from app.database.session import get_db
from app.events.application.services import OutboxOperationsService
from app.events.infrastructure.repositories import SqlAlchemyReliableOutboxRepository


async def outbox_operations_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[OutboxOperationsService]:
    settings = cast(Settings, request.app.state.settings)
    try:
        yield OutboxOperationsService(
            SqlAlchemyReliableOutboxRepository(session),
            lease_seconds=settings.outbox_lease_seconds,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


OutboxOperationsDependency = Annotated[
    OutboxOperationsService, Depends(outbox_operations_dependency)
]
