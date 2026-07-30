from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.common.types import AuthenticatedUser


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Safe metadata scoped to one inbound request."""

    request_id: UUID
    correlation_id: UUID
    started_at: datetime
    client_ip: str | None
    user_agent: str | None
    authenticated_user: AuthenticatedUser | None = None


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "fashion_network_request_context",
    default=None,
)


def maybe_get_request_context() -> RequestContext | None:
    """Return the current context when called inside a request."""
    return _request_context.get()


def get_request_context() -> RequestContext:
    """Return the active request context or fail outside request scope."""
    context = maybe_get_request_context()
    if context is None:
        raise RuntimeError("Request context is not available")
    return context


@contextmanager
def bind_request_context(context: RequestContext) -> Iterator[None]:
    """Bind and reliably reset one request context."""
    token = _request_context.set(context)
    try:
        yield
    finally:
        _request_context.reset(token)
