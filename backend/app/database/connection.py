import logging
from time import perf_counter
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings
from app.observability.metrics import DATABASE_QUERY_DURATION

logger = logging.getLogger(__name__)


def _query_operation(statement: str) -> str:
    operation = statement.lstrip().partition(" ")[0].upper()
    return operation if operation.isalpha() else "OTHER"


def _install_query_diagnostics(
    engine: AsyncEngine,
    *,
    slow_query_threshold_ms: float,
) -> None:
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(
        _connection: Any,
        _cursor: Any,
        _statement: str,
        _parameters: Any,
        context: Any,
        _executemany: bool,
    ) -> None:
        context._fashion_network_query_started = perf_counter()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def after_cursor_execute(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        context: Any,
        _executemany: bool,
    ) -> None:
        started = getattr(context, "_fashion_network_query_started", None)
        if not isinstance(started, float):
            return
        duration_seconds = perf_counter() - started
        operation = _query_operation(statement)
        DATABASE_QUERY_DURATION.labels(operation).observe(duration_seconds)
        duration_ms = duration_seconds * 1000
        if duration_ms >= slow_query_threshold_ms:
            logger.warning(
                "database.slow_query",
                extra={
                    "event": "database.slow_query",
                    "duration_ms": round(duration_ms, 3),
                    "operation": operation,
                },
            )


def create_database_engine(settings: Settings) -> AsyncEngine:
    """Build the process-owned asynchronous SQLAlchemy engine."""
    engine = create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        future=True,
        pool_pre_ping=True,
        pool_recycle=settings.database_pool_recycle_seconds,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        connect_args={
            "command_timeout": settings.database_command_timeout_seconds,
            "server_settings": {"timezone": "UTC"},
        },
    )
    _install_query_diagnostics(
        engine,
        slow_query_threshold_ms=settings.slow_query_threshold_ms,
    )
    return engine


def safe_database_url(database_url: str) -> str:
    """Render a database URL suitable for logs."""
    return make_url(database_url).render_as_string(hide_password=True)
