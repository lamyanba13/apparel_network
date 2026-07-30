from __future__ import annotations

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.constants import CORRELATION_ID_HEADER, REQUEST_ID_HEADER
from app.common.context import RequestContext, bind_request_context
from app.common.utils import generate_uuid7, parse_optional_uuid, utc_now


class RequestContextMiddleware:
    """Create and propagate safe request-scoped context."""

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

        headers = Headers(scope=scope)
        request_id = (
            parse_optional_uuid(headers.get(REQUEST_ID_HEADER)) or generate_uuid7()
        )
        correlation_id = (
            parse_optional_uuid(headers.get(CORRELATION_ID_HEADER)) or request_id
        )
        client = scope.get("client")
        client_ip = client[0] if client else None
        user_agent = headers.get("user-agent")
        if user_agent is not None:
            user_agent = user_agent[:512]

        context = RequestContext(
            request_id=request_id,
            correlation_id=correlation_id,
            started_at=utc_now(),
            client_ip=client_ip,
            user_agent=user_agent,
        )
        scope.setdefault("state", {})["request_context"] = context

        async def send_with_identifiers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers[REQUEST_ID_HEADER] = str(request_id)
                response_headers[CORRELATION_ID_HEADER] = str(correlation_id)
            await send(message)

        with bind_request_context(context):
            await self.app(scope, receive, send_with_identifiers)
