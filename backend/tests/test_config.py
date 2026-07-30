import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_database_pool_configuration_loads_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> None:
    monkeypatch.setenv("FASHION_NETWORK_ENVIRONMENT", "test")
    monkeypatch.setenv("FASHION_NETWORK_DATABASE_URL", database_url)
    monkeypatch.setenv("FASHION_NETWORK_DATABASE_POOL_SIZE", "7")
    monkeypatch.setenv("FASHION_NETWORK_DATABASE_MAX_OVERFLOW", "3")

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.database_pool_size == 7
    assert settings.database_max_overflow == 3


def test_database_url_rejects_synchronous_driver() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://user:password@localhost/database",
        )
