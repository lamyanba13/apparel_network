from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.common.enums import Environment

_DEVELOPMENT_MARKER = "_dev_"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "postgres", "redis", "rabbitmq"}


class Settings(BaseSettings):
    """Fail-fast, environment-aware process configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FASHION_NETWORK_",
        extra="ignore",
        populate_by_name=True,
    )

    application_name: str = "Fashion Network API"
    application_version: str = "0.1.0"
    application_description: str = (
        "Shared API foundation for the Fashion Network inventory network."
    )
    application_contact_name: str = "Fashion Network Engineering"
    application_contact_url: str = "https://example.invalid/contact"
    application_license_name: str = "Proprietary"
    application_license_url: str = "https://example.invalid/license"
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_server_urls: list[str] = Field(
        default_factory=lambda: ["http://localhost:8000"]
    )
    trusted_hosts: list[str] = Field(
        default_factory=lambda: [
            "localhost",
            "127.0.0.1",
            "testserver",
            "api.localhost",
            "backend",
        ]
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:3001",
        ]
    )
    cors_allow_credentials: bool = True
    gzip_minimum_size: int = Field(default=1000, ge=256, le=1_048_576)
    brotli_enabled: bool = True
    brotli_quality: int = Field(default=4, ge=0, le=11)
    etag_enabled: bool = False
    rate_limit_enabled: bool = False
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"
    health_check_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    slow_request_threshold_ms: float = Field(default=1000.0, gt=0)
    slow_query_threshold_ms: float = Field(default=500.0, gt=0)
    opentelemetry_enabled: bool = False
    opentelemetry_service_name: str = "fashion-network-api"
    opentelemetry_exporter_otlp_endpoint: str | None = None
    opentelemetry_trace_sample_ratio: float = Field(default=0.1, ge=0, le=1)
    sentry_enabled: bool = False
    sentry_dsn: SecretStr | None = None
    sentry_trace_sample_rate: float = Field(default=0.0, ge=0, le=1)
    auth_access_token_lifetime_seconds: int = Field(default=900, ge=60, le=3600)
    auth_refresh_token_lifetime_days: int = Field(default=30, ge=1, le=365)
    auth_require_verified_email: bool = True
    auth_login_rate_limit: int = Field(default=5, ge=1, le=1000)
    auth_refresh_rate_limit: int = Field(default=20, ge=1, le=5000)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    public_rate_limit: int = Field(default=120, ge=1, le=10000)
    store_rate_limit: int = Field(default=120, ge=1, le=10000)
    admin_rate_limit: int = Field(default=60, ge=1, le=10000)
    jwt_algorithm: Literal["EdDSA", "ES256"] = "EdDSA"
    jwt_issuer: str = "fashion-network"
    jwt_audience: str = "fashion-network-api"
    jwt_current_key_id: str = "primary"
    jwt_private_key_pem: SecretStr | None = None
    jwt_previous_public_keys: dict[str, str] = Field(default_factory=dict)
    jwt_clock_skew_seconds: int = Field(default=30, ge=0, le=60)

    database_url: str = (
        "postgresql+asyncpg://fashion_network:fashion_network_dev_postgres@localhost:5432/"
        "fashion_network"
    )
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    database_pool_recycle_seconds: int = Field(default=1800, ge=30)
    database_command_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://fashion_network:fashion_network@localhost:5672//"
    meilisearch_url: str = "http://localhost:7700"
    meilisearch_master_key: SecretStr | None = Field(
        default=None,
        validation_alias="MEILI_MASTER_KEY",
    )
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None

    @field_validator("application_version")
    @classmethod
    def validate_application_version(cls, value: str) -> str:
        segments = value.split(".")
        if len(segments) != 3 or not all(segment.isdigit() for segment in segments):
            raise ValueError("application_version must use MAJOR.MINOR.PATCH")
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Unsupported log level")
        return normalized

    @field_validator("database_url")
    @classmethod
    def validate_async_database_url(cls, value: str) -> str:
        """Require PostgreSQL and the approved asyncio driver."""
        try:
            url = make_url(value)
        except (ValueError, TypeError) as error:
            raise ValueError("Invalid database URL") from error
        if url.drivername != "postgresql+asyncpg" or not url.host or not url.database:
            raise ValueError(
                "database_url must use the postgresql+asyncpg SQLAlchemy dialect"
            )
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError("Invalid database port")
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        return cls._validate_service_url(value, {"redis", "rediss"}, "Redis")

    @field_validator("rabbitmq_url")
    @classmethod
    def validate_rabbitmq_url(cls, value: str) -> str:
        return cls._validate_service_url(value, {"amqp", "amqps"}, "RabbitMQ")

    @field_validator(
        "meilisearch_url",
        "s3_endpoint_url",
        "application_contact_url",
        "application_license_url",
    )
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        return cls._validate_service_url(value, {"http", "https"}, "HTTP")

    @field_validator("api_server_urls", "cors_origins")
    @classmethod
    def validate_http_url_list(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("At least one URL is required")
        return [
            cls._validate_service_url(value, {"http", "https"}, "HTTP")
            for value in values
        ]

    @field_validator("trusted_hosts")
    @classmethod
    def validate_trusted_hosts(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().lower() for value in values if value.strip()]
        if not normalized:
            raise ValueError("At least one trusted host is required")
        return normalized

    @field_validator("jwt_issuer", "jwt_audience", "jwt_current_key_id")
    @classmethod
    def validate_jwt_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 200:
            raise ValueError("JWT identifiers must contain 1 to 200 characters")
        return normalized

    @field_validator("jwt_private_key_pem", mode="before")
    @classmethod
    def normalize_private_key(
        cls,
        value: str | SecretStr | None,
    ) -> str | SecretStr | None:
        if isinstance(value, str):
            if not value.strip():
                return None
            return value.replace("\\n", "\n")
        return value

    @field_validator("jwt_previous_public_keys")
    @classmethod
    def normalize_previous_public_keys(
        cls,
        values: dict[str, str],
    ) -> dict[str, str]:
        return {
            key.strip(): value.replace("\\n", "\n")
            for key, value in values.items()
            if key.strip() and value.strip()
        }

    @field_validator("metrics_path")
    @classmethod
    def validate_metrics_path(cls, value: str) -> str:
        if not value.startswith("/") or value == "/" or " " in value:
            raise ValueError("metrics_path must be an absolute non-root path")
        return value

    @field_validator("opentelemetry_exporter_otlp_endpoint")
    @classmethod
    def validate_optional_otlp_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return cls._validate_service_url(value, {"http", "https"}, "OTLP")

    @model_validator(mode="after")
    def validate_environment_security(self) -> Settings:
        sentry_dsn = (
            self.sentry_dsn.get_secret_value() if self.sentry_dsn is not None else ""
        )
        if self.sentry_enabled and not sentry_dsn.strip():
            raise ValueError("sentry_dsn is required when Sentry is enabled")

        if self.environment not in {Environment.STAGING, Environment.PRODUCTION}:
            return self

        private_key = (
            self.jwt_private_key_pem.get_secret_value()
            if self.jwt_private_key_pem is not None
            else ""
        )
        if "PRIVATE KEY" not in private_key:
            raise ValueError(
                "jwt_private_key_pem is required outside local environments"
            )

        protected_urls = {
            "database_url": self.database_url,
            "redis_url": self.redis_url,
            "rabbitmq_url": self.rabbitmq_url,
        }
        for field_name, value in protected_urls.items():
            if field_name == "database_url":
                database_url = make_url(value)
                host = database_url.host
                password = database_url.password
            else:
                service_url = urlsplit(value)
                host = service_url.hostname
                password = service_url.password
            if not password:
                raise ValueError(f"{field_name} must include a secret")
            if _DEVELOPMENT_MARKER in password or host in _LOCAL_HOSTS:
                raise ValueError(f"{field_name} contains local development credentials")

        if "*" in self.trusted_hosts:
            raise ValueError("Wildcard trusted hosts are prohibited")
        if any(not origin.startswith("https://") for origin in self.cors_origins):
            raise ValueError("Non-local CORS origins must use HTTPS")
        secure_urls = [
            *self.api_server_urls,
            self.meilisearch_url,
            self.s3_endpoint_url,
            self.application_contact_url,
            self.application_license_url,
        ]
        if any(not value.startswith("https://") for value in secure_urls):
            raise ValueError("Non-local HTTP service URLs must use HTTPS")
        if any(
            urlsplit(value).hostname in _LOCAL_HOSTS
            or urlsplit(value).hostname == "example.invalid"
            for value in secure_urls
        ):
            raise ValueError("Production URLs must not use local or placeholder hosts")

        secrets = {
            "meilisearch_master_key": self.meilisearch_master_key,
            "s3_secret_access_key": self.s3_secret_access_key,
        }
        for field_name, secret in secrets.items():
            value = secret.get_secret_value() if secret is not None else ""
            if len(value) < 16 or _DEVELOPMENT_MARKER in value:
                raise ValueError(f"{field_name} must contain a production secret")
        if not self.s3_access_key_id:
            raise ValueError("s3_access_key_id is required")
        return self

    @staticmethod
    def _validate_service_url(
        value: str,
        schemes: set[str],
        label: str,
    ) -> str:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as error:
            raise ValueError(f"Invalid {label} URL") from error
        if parsed.scheme not in schemes or not parsed.hostname:
            raise ValueError(f"Invalid {label} URL")
        if port is not None and not 1 <= port <= 65535:
            raise ValueError(f"Invalid {label} port")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""
    return Settings()


settings = get_settings()
