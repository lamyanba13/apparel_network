from __future__ import annotations

import logging
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    """Emit one safe completion event for each HTTP request."""

    def __init__(self, app: ASGIApp, *, slow_request_threshold_ms: float) -> None:
        self.app = app
        self.slow_request_threshold_ms = slow_request_threshold_ms

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        status_code = 500

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            duration_ms = round((perf_counter() - started) * 1000, 3)
            log = (
                logger.warning
                if duration_ms >= self.slow_request_threshold_ms
                else logger.info
            )
            event = (
                "http.slow_request"
                if duration_ms >= self.slow_request_threshold_ms
                else "http.request_completed"
            )
            log(
                event,
                extra={
                    "event": event,
                    "http_method": scope["method"],
                    "http_path": scope["path"],
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
