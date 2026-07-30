from __future__ import annotations

import logging

from app.common.events import DomainEvent, EventPublisher
from app.modules.identity.domain import (
    AuthenticationFailed,
    AuthenticationSucceeded,
    LogoutCompleted,
    RefreshReuseDetected,
    RefreshRotated,
)
from app.observability.metrics import (
    AUTHENTICATION_FAILED,
    AUTHENTICATION_LOGOUT,
    AUTHENTICATION_REFRESH_REUSE,
    AUTHENTICATION_REFRESHED,
    AUTHENTICATION_SUCCEEDED,
)

logger = logging.getLogger(__name__)


class AuthenticationEventPublisher(EventPublisher):
    """In-process authentication event consumer for logs and metrics."""

    async def publish(self, event: DomainEvent) -> None:
        extra = {
            "event": event.event_name,
            "event_id": str(event.event_id),
            "schema_version": event.schema_version,
            **event.payload,
        }
        if isinstance(event, AuthenticationSucceeded):
            AUTHENTICATION_SUCCEEDED.inc()
            logger.info(event.event_name, extra=extra)
        elif isinstance(event, AuthenticationFailed):
            AUTHENTICATION_FAILED.inc()
            logger.warning(event.event_name, extra=extra)
        elif isinstance(event, RefreshRotated):
            AUTHENTICATION_REFRESHED.inc()
            logger.info(event.event_name, extra=extra)
        elif isinstance(event, RefreshReuseDetected):
            AUTHENTICATION_REFRESH_REUSE.inc()
            logger.warning(event.event_name, extra=extra)
        elif isinstance(event, LogoutCompleted):
            AUTHENTICATION_LOGOUT.inc()
            logger.info(event.event_name, extra=extra)
