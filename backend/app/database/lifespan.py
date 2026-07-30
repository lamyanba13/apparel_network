from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from time import perf_counter

from fastapi import FastAPI

from app.core.config import Settings
from app.database.connection import create_database_engine, safe_database_url
from app.database.health import check_database_connection, get_migration_status
from app.database.session import DatabaseSessionManager
from app.health import create_health_service
from app.observability import capture_exception, configure_sqlalchemy_telemetry

logger = logging.getLogger(__name__)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_database_lifespan(settings: Settings) -> Lifespan:
    """Create a FastAPI lifespan that owns database startup and shutdown."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        startup_started = perf_counter()
        engine = create_database_engine(settings)
        manager = DatabaseSessionManager(engine)
        application.state.database = manager
        health = create_health_service(engine, settings)
        application.state.health = health
        configure_sqlalchemy_telemetry(engine, settings)

        logger.info(
            "database.startup url=%s pool_size=%s max_overflow=%s",
            safe_database_url(settings.database_url),
            settings.database_pool_size,
            settings.database_max_overflow,
        )

        try:
            if not await check_database_connection(engine):
                raise RuntimeError(
                    "PostgreSQL is unavailable during application startup"
                )

            migration_status = await get_migration_status(engine)
            logger.info(
                "database.migration_status current_heads=%s expected_heads=%s "
                "is_current=%s",
                migration_status.current_heads,
                migration_status.expected_heads,
                migration_status.is_current,
            )
            health.startup_complete = True
            logger.info(
                "application.startup_completed",
                extra={
                    "event": "application.startup_completed",
                    "duration_ms": round(
                        (perf_counter() - startup_started) * 1000,
                        3,
                    ),
                },
            )
            yield
        except Exception as error:
            logger.exception("database.startup_or_runtime_failed")
            capture_exception(error)
            raise
        finally:
            shutdown_started = perf_counter()
            health.startup_complete = False
            await manager.close()
            logger.info(
                "application.shutdown_completed",
                extra={
                    "event": "application.shutdown_completed",
                    "duration_ms": round(
                        (perf_counter() - shutdown_started) * 1000,
                        3,
                    ),
                },
            )

    return lifespan
