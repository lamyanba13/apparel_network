from __future__ import annotations

from importlib import import_module
from typing import Protocol, cast

from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_UNCOMPRESSED_CONTENT_PREFIXES = (
    "audio/",
    "image/",
    "video/",
)
_UNCOMPRESSED_CONTENT_TYPES = {
    "application/gzip",
    "application/zip",
    "text/event-stream",
}


class BrotliCompressor(Protocol):
    """Callable shape exposed by the optional Brotli binding."""

    def __call__(self, data: bytes, *, quality: int) -> bytes: ...


def load_brotli_compressor() -> BrotliCompressor | None:
    """Load Brotli when installed and allow a transparent GZip fallback."""
    try:
        module = import_module("brotli")
    except ImportError:
        return None
    return cast(BrotliCompressor, module.compress)


def _encoding_quality(header: str, encoding: str) -> float:
    wildcard_quality = 0.0
    for entry in header.lower().split(","):
        parts = [part.strip() for part in entry.split(";")]
        name = parts[0]
        quality = 1.0
        for parameter in parts[1:]:
            if parameter.startswith("q="):
                try:
                    quality = float(parameter.removeprefix("q="))
                except ValueError:
                    quality = 0.0
        if name == encoding:
            return quality
        if name == "*":
            wildcard_quality = quality
    return wildcard_quality


class AdaptiveCompressionMiddleware:
    """Prefer Brotli for ordinary responses and fall back safely to GZip."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        minimum_size: int,
        gzip_compresslevel: int = 9,
        brotli_quality: int = 4,
        brotli_enabled: bool = True,
    ) -> None:
        self.app = app
        self.gzip = GZipMiddleware(
            app,
            minimum_size=minimum_size,
            compresslevel=gzip_compresslevel,
        )
        self.minimum_size = minimum_size
        self.brotli_quality = brotli_quality
        self.brotli_compressor = load_brotli_compressor() if brotli_enabled else None

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        accepted = Headers(scope=scope).get("accept-encoding", "")
        if self.brotli_compressor is not None and _encoding_quality(accepted, "br") > 0:
            await self._send_brotli(scope, receive, send)
            return
        if _encoding_quality(accepted, "gzip") > 0:
            await self.gzip(scope, receive, send)
            return
        await self.app(scope, receive, send)

    async def _send_brotli(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        start_message: Message | None = None
        passthrough = False

        async def compress_response(message: Message) -> None:
            nonlocal passthrough, start_message
            if message["type"] == "http.response.start":
                start_message = message
                return

            if start_message is None or message["type"] != "http.response.body":
                await send(message)
                return

            if passthrough:
                await send(message)
                return

            if message.get("more_body", False):
                passthrough = True
                await send(start_message)
                await send(message)
                return

            body = message.get("body", b"")
            headers = Headers(raw=start_message.get("headers", []))
            content_type = headers.get("content-type", "").split(";", 1)[0]
            should_compress = (
                200 <= start_message["status"] < 300
                and len(body) >= self.minimum_size
                and "content-encoding" not in headers
                and content_type not in _UNCOMPRESSED_CONTENT_TYPES
                and not content_type.startswith(_UNCOMPRESSED_CONTENT_PREFIXES)
            )
            if not should_compress or self.brotli_compressor is None:
                await send(start_message)
                await send(message)
                return

            compressed = self.brotli_compressor(
                body,
                quality=self.brotli_quality,
            )
            mutable_headers = MutableHeaders(scope=start_message)
            mutable_headers["Content-Encoding"] = "br"
            mutable_headers["Content-Length"] = str(len(compressed))
            mutable_headers.add_vary_header("Accept-Encoding")
            await send(start_message)
            await send({**message, "body": compressed})

        await self.app(scope, receive, compress_response)
