from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from app.common.events import DomainEvent, EventPublisher
from app.modules.stores.domain.search_events import StoreSearchSyncRequested

_SYNC_EVENTS = {
    "store.created": "index",
    "store.updated": "update",
    "store.submitted": "delete",
    "store.verified": "index",
    "store.suspended": "delete",
    "store.closed": "delete",
    "store.deleted": "delete",
    "store.logo.uploaded": "update",
    "store.banner.uploaded": "update",
    "store.gallery.uploaded": "update",
    "store.media.deleted": "update",
    "store.hours.created": "update",
    "store.hours.updated": "update",
    "store.hours.deleted": "update",
}

logger = logging.getLogger(__name__)


class StoreEventPublisher(EventPublisher):
    """Initial in-process Store event consumer for structured audit logs."""

    def __init__(
        self,
        dispatcher: Callable[[StoreSearchSyncRequested], None] | None = None,
    ) -> None:
        self._dispatcher = dispatcher

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
        operation = _SYNC_EVENTS.get(event.event_name)
        store_id = event.payload.get("store_id")
        if operation is not None and isinstance(store_id, str):
            request = StoreSearchSyncRequested(
                store_id=UUID(store_id),
                operation=operation,
                occurred_at=event.occurred_at,
                correlation_id=event.correlation_id,
            )
            if self._dispatcher is not None:
                self._dispatcher(request)
