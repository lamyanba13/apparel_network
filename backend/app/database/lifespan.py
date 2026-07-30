from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings
from app.database.connection import create_database_engine, safe_database_url
from app.database.health import check_database_connection, get_migration_status
from app.database.session import DatabaseSessionManager

logger = logging.getLogger(__name__)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_database_lifespan(settings: Settings) -> Lifespan:
    """Create a FastAPI lifespan that owns database startup and shutdown."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(settings)
        manager = DatabaseSessionManager(engine)
        application.state.database = manager

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
            yield
        except Exception:
            logger.exception("database.startup_or_runtime_failed")
            raise
        finally:
            logger.info("database.shutdown")
            await manager.close()

    return lifespan
