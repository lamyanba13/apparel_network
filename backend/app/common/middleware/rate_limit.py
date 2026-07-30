from __future__ import annotations

import json
from collections.abc import Callable
from http import HTTPStatus

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.context import RequestContext
from app.common.errors import ErrorCode, ProblemDetails
from app.common.rate_limiting import RateLimiter, RateLimitScope

RateLimitScopeResolver = Callable[[Scope], RateLimitScope]


def public_rate_limit_scope(_: Scope) -> RateLimitScope:
    """Use public policy until a reviewed route classifier is supplied."""
    return RateLimitScope.PUBLIC


class RateLimitMiddleware:
    """Optional transport limiter backed by an injected ephemeral adapter."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool,
        limiter: RateLimiter | None = None,
        scope_resolver: RateLimitScopeResolver = public_rate_limit_scope,
    ) -> None:
        if enabled and limiter is None:
            raise RuntimeError("Rate limiting is enabled without a RateLimiter")
        self.app = app
        self.enabled = enabled
        self.limiter = limiter
        self.scope_resolver = scope_resolver

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if not self.enabled or self.limiter is None or scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        context = state.get("request_context")
        client_ip = context.client_ip if isinstance(context, RequestContext) else None
        decision = await self.limiter.check(
            scope=self.scope_resolver(scope),
            key=client_ip or "unknown",
        )
        if not decision.is_allowed:
            await self._send_rejection(
                scope, context, decision.retry_after_seconds, send
            )
            return

        async def add_rate_limit_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["RateLimit-Limit"] = str(decision.limit)
                headers["RateLimit-Remaining"] = str(decision.remaining)
            await send(message)

        await self.app(scope, receive, add_rate_limit_headers)

    @staticmethod
    async def _send_rejection(
        scope: Scope,
        context: object,
        retry_after_seconds: int | None,
        send: Send,
    ) -> None:
        request_id = (
            str(context.request_id)
            if isinstance(context, RequestContext)
            else "unavailable"
        )
        problem = ProblemDetails(
            type="https://docs.example.invalid/problems/rate-limit-exceeded",
            title="Too many requests",
            status=HTTPStatus.TOO_MANY_REQUESTS,
            code=ErrorCode.RATE_LIMIT_EXCEEDED.value,
            detail="The request limit has been exceeded. Retry later.",
            instance=scope["path"],
            request_id=request_id,
        )
        body = json.dumps(problem.model_dump(mode="json")).encode()
        headers = [
            (b"content-type", b"application/problem+json"),
            (b"content-length", str(len(body)).encode()),
        ]
        if retry_after_seconds is not None:
            headers.append((b"retry-after", str(retry_after_seconds).encode()))
        await send(
            {
                "type": "http.response.start",
                "status": HTTPStatus.TOO_MANY_REQUESTS,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})
