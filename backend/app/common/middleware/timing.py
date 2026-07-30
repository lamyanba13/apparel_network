from __future__ import annotations

from time import perf_counter

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.constants import REQUEST_TIME_HEADER


class RequestTimingMiddleware:
    """Expose server processing time without leaking internal details."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

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

        async def add_timing_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                duration_ms = (perf_counter() - started) * 1000
                headers = MutableHeaders(scope=message)
                headers[REQUEST_TIME_HEADER] = f"{duration_ms:.3f}"
            await send(message)

        await self.app(scope, receive, add_timing_header)
