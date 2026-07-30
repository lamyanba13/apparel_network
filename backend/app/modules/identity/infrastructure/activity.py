from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from starlette.types import ASGIApp, Receive, Scope, Send

from app.database.session import DatabaseSessionManager
from app.modules.identity.domain import parse_device
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyRefreshSessionRepository,
)

logger = logging.getLogger(__name__)


class SessionActivityMiddleware:
    """Persist authenticated activity with one atomic, throttled write."""

    def __init__(self, app: ASGIApp, *, throttle_seconds: int = 300) -> None:
        self.app = app
        self._throttle = timedelta(seconds=throttle_seconds)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)
        if scope["type"] != "http":
            return
        state = scope.get("state", {})
        session_id = state.get("authenticated_session_id")
        if not isinstance(session_id, UUID):
            return
        application = scope["app"]
        manager = cast(DatabaseSessionManager, application.state.database)
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", ())
        }
        user_agent = headers.get("user-agent", "Unknown user agent")[:1024]
        client = scope.get("client")
        client_ip = client[0] if client is not None else "0.0.0.0"
        device = parse_device(user_agent)
        observed_at = datetime.now(UTC)
        try:
            async with manager.session_factory() as db_session, db_session.begin():
                await SqlAlchemyRefreshSessionRepository(db_session).touch_activity(
                    session_id,
                    observed_at=observed_at,
                    write_before=observed_at - self._throttle,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    browser=device.browser,
                    operating_system=device.operating_system,
                    device_type=device.device_type,
                    platform=device.platform,
                )
        except Exception:
            # Activity is best-effort and must not turn a completed API call into
            # an application failure. No request metadata or credentials are logged.
            logger.exception(
                "identity.session_activity_update_failed",
                extra={"event": "identity.session_activity_update_failed"},
            )
