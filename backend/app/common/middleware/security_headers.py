from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.enums import Environment
from app.common.security import build_security_headers


class SecurityHeadersMiddleware:
    """Apply the approved baseline response security headers."""

    def __init__(self, app: ASGIApp, *, environment: Environment) -> None:
        self.app = app
        self.headers = build_security_headers(environment)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def add_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.headers.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, add_security_headers)
