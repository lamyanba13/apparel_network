from __future__ import annotations

import os

import pytest

from app.core.config import Settings


@pytest.fixture
def database_url() -> str:
    return os.getenv(
        "FASHION_NETWORK_DATABASE_URL",
        "postgresql+asyncpg://fashion_network:fashion_network_dev_postgres@"
        "localhost:5432/fashion_network",
    )


@pytest.fixture
def test_settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        database_pool_size=1,
        database_max_overflow=0,
    )
