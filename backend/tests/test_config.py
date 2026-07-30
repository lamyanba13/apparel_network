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


def test_port_validation_rejects_out_of_range_value() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_port=70000)


def test_observability_settings_are_safe_by_default() -> None:
    settings = Settings(_env_file=None, environment="test")

    assert settings.metrics_enabled is True
    assert settings.opentelemetry_enabled is False
    assert settings.sentry_enabled is False
    assert settings.slow_request_threshold_ms == 1000
    assert settings.slow_query_threshold_ms == 500


def test_sentry_requires_dsn_when_enabled() -> None:
    with pytest.raises(ValidationError, match="sentry_dsn"):
        Settings(_env_file=None, environment="test", sentry_enabled=True)


def test_production_rejects_local_or_missing_service_secrets() -> None:
    with pytest.raises(ValidationError, match=r"development credentials|secret"):
        Settings(
            _env_file=None,
            environment="production",
            cors_origins=["https://app.example.com"],
            trusted_hosts=["api.example.com"],
        )


def test_production_accepts_explicit_secure_service_configuration() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url=(
            "postgresql+asyncpg://fashion:database-secret@db.internal:5432/fashion"
        ),
        redis_url="rediss://:redis-secret@cache.internal:6380/0",
        rabbitmq_url="amqps://fashion:rabbit-secret@mq.internal:5671/fashion",
        meilisearch_url="https://search.internal",
        meilisearch_master_key="production-search-secret",
        s3_endpoint_url="https://storage.internal",
        s3_access_key_id="fashion-production",
        s3_secret_access_key="production-storage-secret",
        cors_origins=["https://app.example.com"],
        trusted_hosts=["api.example.com"],
        api_server_urls=["https://api.example.com"],
        application_contact_url="https://app.example.com/contact",
        application_license_url="https://app.example.com/license",
    )

    assert settings.environment == "production"
