from __future__ import annotations

import logging

from app.common.events import DomainEvent, EventPublisher

logger = logging.getLogger(__name__)


class StoreEventPublisher(EventPublisher):
    """Initial in-process Store event consumer for structured audit logs."""

    async def publish(self, event: DomainEvent) -> None:
        logger.info(
            event.event_name,
            extra={
                "event": event.event_name,
                "event_id": str(event.event_id),
                "event_occurred_at": event.occurred_at.isoformat(),
                "event_correlation_id": (
                    str(event.correlation_id)
                    if event.correlation_id is not None
                    else None
                ),
                "schema_version": event.schema_version,
                **event.payload,
            },
        )
