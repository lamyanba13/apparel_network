from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationStatus:
    """Describe database and source migration heads."""

    current_heads: tuple[str, ...]
    expected_heads: tuple[str, ...]

    @property
    def is_current(self) -> bool:
        return set(self.current_heads) == set(self.expected_heads)


async def check_database_connection(engine: AsyncEngine) -> bool:
    """Check PostgreSQL connectivity without changing authoritative state."""
    try:
        async with engine.connect() as connection:
            result = cast(int | None, await connection.scalar(text("SELECT 1")))
        return result == 1
    except (SQLAlchemyError, TimeoutError, OSError):
        logger.exception("database.connection_failed")
        return False


async def check_database_session(session: AsyncSession) -> bool:
    """Check connectivity through a request-scoped session."""
    try:
        result = cast(int | None, await session.scalar(text("SELECT 1")))
        return result == 1
    except (SQLAlchemyError, TimeoutError, OSError):
        logger.exception("database.session_health_failed")
        return False


def _current_migration_heads(connection: Connection) -> tuple[str, ...]:
    context = MigrationContext.configure(connection)
    return tuple(context.get_current_heads())


async def get_migration_status(
    engine: AsyncEngine,
    *,
    alembic_config_path: Path | None = None,
) -> MigrationStatus:
    """Compare applied database heads with the repository migration heads."""
    config_path = alembic_config_path or (
        Path(__file__).resolve().parents[2] / "alembic.ini"
    )
    alembic_config = Config(config_path)
    script = ScriptDirectory.from_config(alembic_config)

    async with engine.connect() as connection:
        current_heads = await connection.run_sync(_current_migration_heads)

    return MigrationStatus(
        current_heads=current_heads,
        expected_heads=tuple(script.get_heads()),
    )
