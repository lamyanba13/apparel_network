from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import DomainEvent, EventPublisher
from app.modules.products.domain import OutboxStatus
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.observability.metrics import OUTBOX_EVENTS_CREATED


class TransactionalOutboxPublisher(EventPublisher):
    """Persist a domain event in the business transaction before delegating."""

    def __init__(
        self, session: AsyncSession, *, delegate: EventPublisher | None = None
    ) -> None:
        self._session = session
        self._delegate = delegate

    async def publish(self, event: DomainEvent) -> None:
        payload = cast(dict[str, object], dict(event.payload))
        aggregate_type = event.event_name.split(".", 1)[0]
        aggregate_id = _aggregate_id(aggregate_type, payload, event.event_id)
        self._session.add(
            EventOutboxModel(
                id=event.event_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_name=event.event_name,
                payload=payload,
                occurred_at=event.occurred_at,
                available_at=event.occurred_at,
                status=OutboxStatus.PENDING,
            )
        )
        await self._session.flush()
        OUTBOX_EVENTS_CREATED.inc()
        if self._delegate is not None:
            await self._delegate.publish(event)


def _aggregate_id(
    aggregate_type: str, payload: dict[str, object], fallback: UUID
) -> UUID:
    candidates = (
        f"{aggregate_type}_id",
        "inventory_id",
        "price_id",
        "price_list_id",
        "notification_id",
    )
    for key in candidates:
        value = payload.get(key)
        if value is not None:
            try:
                return UUID(str(value))
            except ValueError:
                continue
    return fallback
