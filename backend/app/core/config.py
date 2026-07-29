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


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""
    return Settings()


settings = get_settings()
