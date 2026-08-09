from __future__ import annotations

import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import Settings


@pytest.fixture
def database_url() -> str:
    return os.getenv(
        "FASHION_NETWORK_DATABASE_URL",
        "postgresql+asyncpg://fashion_network:fashion_network_dev_postgres@"
        "localhost:5432/fashion_network",
    )


@pytest.fixture
def test_private_key_pem() -> str:
    private_key = Ed25519PrivateKey.generate()
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def test_settings(database_url: str, test_private_key_pem: str) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        redis_url=os.getenv(
            "FASHION_NETWORK_TEST_REDIS_URL",
            "redis://:fashion_network_dev_redis@localhost:6379/0",
        ),
        database_pool_size=1,
        database_max_overflow=0,
        opentelemetry_exporter_otlp_endpoint=None,
        jwt_private_key_pem=test_private_key_pem,
        s3_endpoint_url="http://localhost:9000",
        s3_access_key_id="fashion_network",
        s3_secret_access_key="fashion_network_dev_minio_secret",
    )
