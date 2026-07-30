from __future__ import annotations

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.caching import if_none_match_matches

_ENTITY_HEADERS = {
    b"content-encoding",
    b"content-language",
    b"content-length",
    b"content-type",
}


class ETagMiddleware:
    """Optionally turn matching, explicitly tagged GET/HEAD responses into 304s."""

    def __init__(self, app: ASGIApp, *, enabled: bool) -> None:
        self.app = app
        self.enabled = enabled

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if (
            not self.enabled
            or scope["type"] != "http"
            or scope["method"] not in {"GET", "HEAD"}
        ):
            await self.app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        if_none_match = request_headers.get("if-none-match")
        suppress_body = False

        async def handle_conditional_response(message: Message) -> None:
            nonlocal suppress_body
            if message["type"] == "http.response.start":
                response_headers = Headers(raw=message.get("headers", []))
                etag = response_headers.get("etag")
                if (
                    if_none_match is not None
                    and etag is not None
                    and if_none_match_matches(if_none_match, etag)
                ):
                    message = {
                        **message,
                        "status": 304,
                        "headers": [
                            (name, value)
                            for name, value in message.get("headers", [])
                            if name.lower() not in _ENTITY_HEADERS
                        ],
                    }
                    suppress_body = True
                await send(message)
                return

            if message["type"] == "http.response.body" and suppress_body:
                if not message.get("more_body", False):
                    await send({"type": "http.response.body", "body": b""})
                return
            await send(message)

        await self.app(scope, receive, handle_conditional_response)
