import logging
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.main import create_application


@pytest.fixture
def application(test_settings: Any) -> Iterator[FastAPI]:
    app = create_application(test_settings)
    publisher_logger = logging.getLogger("app.modules.stores.infrastructure.events")
    publisher_logger_was_disabled = publisher_logger.disabled
    publisher_logger.disabled = False
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        publisher_logger.disabled = publisher_logger_was_disabled


@pytest.fixture
async def async_client(application: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=application)
    async with (
        application.router.lifespan_context(application),
        AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client,
    ):
        yield client


@pytest.fixture
def test_client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(application) as client:
        yield client


@pytest.fixture
def override_dependency(
    application: FastAPI,
) -> Callable[[Callable[..., Any], Callable[..., Any]], None]:
    def register(
        dependency: Callable[..., Any],
        replacement: Callable[..., Any],
    ) -> None:
        application.dependency_overrides[dependency] = replacement

    return register
