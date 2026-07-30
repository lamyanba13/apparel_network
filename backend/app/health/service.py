from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Literal, cast

import httpx
from kombu import Connection
from redis import asyncio as redis_async
from sqlalchemy.ext.asyncio import AsyncEngine

from app.common.config import Settings
from app.database.health import check_database_connection
from app.observability.metrics import DEPENDENCY_CHECK_DURATION, DEPENDENCY_UP

logger = logging.getLogger(__name__)

DependencyName = Literal["postgresql", "rabbitmq", "redis", "meilisearch", "minio"]
DependencyCheck = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class DependencyCheckResult:
    status: Literal["healthy", "unhealthy"]
    latency_ms: float


@dataclass(frozen=True)
class ReadinessResult:
    status: Literal["ready", "not_ready"]
    checks: dict[DependencyName, DependencyCheckResult]


async def _check_redis(settings: Settings) -> bool:
    client = redis_async.from_url(  # type: ignore[no-untyped-call]
        settings.redis_url,
        socket_connect_timeout=settings.health_check_timeout_seconds,
        socket_timeout=settings.health_check_timeout_seconds,
    )
    try:
        return bool(await client.ping())
    finally:
        await client.aclose()


def _check_rabbitmq_sync(settings: Settings) -> bool:
    connection = Connection(
        settings.rabbitmq_url,
        connect_timeout=settings.health_check_timeout_seconds,
    )
    try:
        connection.ensure_connection(max_retries=0)
        return bool(connection.connected)
    finally:
        connection.close()


async def _check_rabbitmq(settings: Settings) -> bool:
    return await asyncio.to_thread(_check_rabbitmq_sync, settings)


async def _check_http(url: str, settings: Settings) -> bool:
    timeout = httpx.Timeout(settings.health_check_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url)
        return response.is_success


def create_health_service(
    engine: AsyncEngine,
    settings: Settings,
) -> HealthService:
    return HealthService(
        checks={
            "postgresql": lambda: check_database_connection(engine),
            "rabbitmq": lambda: _check_rabbitmq(settings),
            "redis": lambda: _check_redis(settings),
            "meilisearch": lambda: _check_http(
                f"{settings.meilisearch_url.rstrip('/')}/health",
                settings,
            ),
            "minio": lambda: _check_http(
                f"{settings.s3_endpoint_url.rstrip('/')}/minio/health/ready",
                settings,
            ),
        },
        timeout_seconds=settings.health_check_timeout_seconds,
    )


class HealthService:
    """Evaluate process startup and bounded dependency readiness."""

    def __init__(
        self,
        *,
        checks: dict[DependencyName, DependencyCheck],
        timeout_seconds: float,
    ) -> None:
        self._checks = checks
        self._timeout_seconds = timeout_seconds
        self.startup_complete = False

    async def _run_check(
        self,
        name: DependencyName,
        check: DependencyCheck,
    ) -> tuple[DependencyName, DependencyCheckResult]:
        started = perf_counter()
        healthy = False
        try:
            healthy = await asyncio.wait_for(
                check(),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            healthy = False
            logger.warning(
                "health.dependency_timeout",
                extra={
                    "dependency": name,
                    "event": "health.dependency_timeout",
                },
            )
        except Exception:
            # Readiness is the failure boundary. Dependency/client exceptions can
            # contain credential-bearing URLs, so log only the safe check name.
            healthy = False
            logger.warning(
                "health.dependency_unavailable",
                extra={
                    "dependency": name,
                    "event": "health.dependency_unavailable",
                },
            )
        latency_seconds = perf_counter() - started
        DEPENDENCY_UP.labels(name).set(1 if healthy else 0)
        DEPENDENCY_CHECK_DURATION.labels(name).observe(latency_seconds)
        return (
            name,
            DependencyCheckResult(
                status="healthy" if healthy else "unhealthy",
                latency_ms=round(latency_seconds * 1000, 3),
            ),
        )

    async def readiness(self) -> ReadinessResult:
        results = await asyncio.gather(
            *(self._run_check(name, check) for name, check in self._checks.items())
        )
        checks = cast(
            dict[DependencyName, DependencyCheckResult],
            dict(results),
        )
        ready = all(result.status == "healthy" for result in checks.values())
        return ReadinessResult(
            status="ready" if ready else "not_ready",
            checks=checks,
        )
