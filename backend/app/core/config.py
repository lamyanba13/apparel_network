from functools import lru_cache
from typing import Literal

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
        "postgresql+psycopg://fashion_network:fashion_network@localhost:5432/"
        "fashion_network"
    )
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://fashion_network:fashion_network@localhost:5672//"
    meilisearch_url: str = "http://localhost:7700"
    s3_endpoint_url: str = "http://localhost:9000"


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""
    return Settings()


settings = get_settings()
