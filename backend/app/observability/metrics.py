from __future__ import annotations

from time import perf_counter
from typing import cast

from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HTTP_REQUESTS = Counter(
    "fashion_network_http_requests_total",
    "Completed HTTP requests.",
    ("method", "route", "status_code"),
)
HTTP_REQUEST_DURATION = Histogram(
    "fashion_network_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
)
DEPENDENCY_UP = Gauge(
    "fashion_network_dependency_up",
    "Whether an application dependency passed its latest readiness check.",
    ("dependency",),
)
DEPENDENCY_CHECK_DURATION = Histogram(
    "fashion_network_dependency_check_duration_seconds",
    "Dependency readiness check duration in seconds.",
    ("dependency",),
)
DATABASE_POOL_SIZE = Gauge(
    "fashion_network_database_pool_size",
    "Configured SQLAlchemy connection pool size.",
)
DATABASE_POOL_CHECKED_IN = Gauge(
    "fashion_network_database_pool_checked_in",
    "Idle SQLAlchemy pool connections.",
)
DATABASE_POOL_CHECKED_OUT = Gauge(
    "fashion_network_database_pool_checked_out",
    "Checked-out SQLAlchemy pool connections.",
)
DATABASE_POOL_OVERFLOW = Gauge(
    "fashion_network_database_pool_overflow",
    "Current SQLAlchemy overflow connections.",
)
DATABASE_QUERY_DURATION = Histogram(
    "fashion_network_database_query_duration_seconds",
    "SQL statement duration by operation.",
    ("operation",),
)
WORKER_UP = Gauge(
    "fashion_network_worker_up",
    "Worker availability placeholder; worker exporters set this in Phase 2.",
)
WORKER_ACTIVE_TASKS = Gauge(
    "fashion_network_worker_active_tasks",
    "Active worker task placeholder; worker exporters set this in Phase 2.",
)

WORKER_UP.set(0)
WORKER_ACTIVE_TASKS.set(0)


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    if isinstance(route, Route):
        return route.path
    return "unmatched"


class MetricsMiddleware:
    """Record low-cardinality HTTP RED metrics."""

    def __init__(self, app: ASGIApp, *, enabled: bool = True) -> None:
        self.app = app
        self.enabled = enabled

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http" or not self.enabled:
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
            route = _route_template(scope)
            method = cast(str, scope["method"])
            HTTP_REQUESTS.labels(method, route, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(method, route).observe(
                perf_counter() - started
            )


def update_database_pool_metrics(engine: AsyncEngine) -> None:
    """Snapshot QueuePool diagnostics without exposing connection details."""
    pool = cast(QueuePool, engine.sync_engine.pool)
    DATABASE_POOL_SIZE.set(pool.size())
    DATABASE_POOL_CHECKED_IN.set(pool.checkedin())
    DATABASE_POOL_CHECKED_OUT.set(pool.checkedout())
    DATABASE_POOL_OVERFLOW.set(pool.overflow())


def metrics_response(request: Request) -> Response:
    """Render the Prometheus exposition format."""
    manager = getattr(request.app.state, "database", None)
    if manager is not None:
        update_database_pool_metrics(manager.engine)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
