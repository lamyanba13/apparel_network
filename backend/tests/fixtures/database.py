import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _database_url() -> str:
    return os.getenv(
        "FASHION_NETWORK_DATABASE_URL",
        "postgresql+asyncpg://fashion_network:fashion_network_dev_postgres@"
        "localhost:5432/fashion_network",
    )


@pytest.fixture(scope="session")
def database_url() -> str:
    return _database_url()


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    database_url = _database_url()
    get_settings.cache_clear()
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    try:
        yield database_url
    finally:
        get_settings.cache_clear()


@pytest.fixture(scope="session")
async def async_engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        migrated_database,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def session_factory(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        transaction = await session.begin()
        try:
            yield session
        finally:
            if transaction.is_active:
                await transaction.rollback()
