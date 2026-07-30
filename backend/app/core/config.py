from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated process configuration for the foundation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FASHION_NETWORK_",
        extra="ignore",
    )

    application_name: str = "Fashion Network API"
    application_version: str = "0.1.0"
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
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
    s3_endpoint_url: str = "http://localhost:9000"

    @field_validator("database_url")
    @classmethod
    def validate_async_database_url(cls, value: str) -> str:
        """Require the approved PostgreSQL asyncio driver."""
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "database_url must use the postgresql+asyncpg SQLAlchemy dialect"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""
    return Settings()


settings = get_settings()
