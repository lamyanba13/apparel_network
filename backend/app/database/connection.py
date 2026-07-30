from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings


def create_database_engine(settings: Settings) -> AsyncEngine:
    """Build the process-owned asynchronous SQLAlchemy engine."""
    return create_async_engine(
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


def safe_database_url(database_url: str) -> str:
    """Render a database URL suitable for logs."""
    return make_url(database_url).render_as_string(hide_password=True)
