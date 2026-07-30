from typing import Annotated
from uuid import UUID, uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.common.api.dependencies import request_context_dependency
from app.common.context import (
    RequestContext,
    get_request_context,
    maybe_get_request_context,
)
from app.common.enums import Environment
from app.common.security import build_security_headers
from app.core.config import Settings
from app.main import create_application


def test_request_identifiers_and_context_are_scoped_to_one_request(
    test_settings: Settings,
) -> None:
    application = create_application(test_settings)

    @application.get("/_test/context", include_in_schema=False)
    async def context_endpoint(
        context: Annotated[RequestContext, Depends(request_context_dependency)],
    ) -> dict[str, str | None]:
        return {
            "request_id": str(context.request_id),
            "correlation_id": str(context.correlation_id),
            "client_ip": context.client_ip,
            "user_agent": context.user_agent,
        }

    request_id = uuid4()
    correlation_id = uuid4()
    with TestClient(application) as client:
        response = client.get(
            "/_test/context",
            headers={
                "X-Request-ID": str(request_id),
                "X-Correlation-ID": str(correlation_id),
                "User-Agent": "phase-1.4-test",
            },
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == str(request_id)
    assert response.headers["X-Correlation-ID"] == str(correlation_id)
    assert response.json() == {
        "request_id": str(request_id),
        "correlation_id": str(correlation_id),
        "client_ip": "testclient",
        "user_agent": "phase-1.4-test",
    }
    assert maybe_get_request_context() is None
    with pytest.raises(RuntimeError, match="not available"):
        get_request_context()


def test_invalid_request_identifier_is_replaced_with_uuid7(
    test_settings: Settings,
) -> None:
    with TestClient(create_application(test_settings)) as client:
        response = client.get("/health", headers={"X-Request-ID": "not-a-uuid"})

    generated = UUID(response.headers["X-Request-ID"])
    assert generated.version == 7
    assert response.headers["X-Correlation-ID"] == str(generated)


def test_transport_middleware_applies_security_timing_and_cors(
    test_settings: Settings,
) -> None:
    with TestClient(create_application(test_settings)) as client:
        preflight_response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        health_response = client.get("/health")

    assert preflight_response.status_code == 200
    assert (
        preflight_response.headers["access-control-allow-origin"]
        == "http://localhost:3000"
    )
    assert health_response.headers["x-content-type-options"] == "nosniff"
    assert health_response.headers["x-frame-options"] == "DENY"
    assert float(health_response.headers["X-Process-Time-Ms"]) >= 0
    assert "strict-transport-security" not in health_response.headers


def test_gzip_and_trusted_host_middleware_are_enforced(
    test_settings: Settings,
) -> None:
    application = create_application(test_settings)

    @application.get("/_test/large", include_in_schema=False)
    async def large_response() -> dict[str, str]:
        return {"content": "x" * 2000}

    with TestClient(application) as client:
        compressed = client.get(
            "/_test/large",
            headers={"Accept-Encoding": "gzip"},
        )
        rejected = client.get("/health", headers={"Host": "untrusted.example"})

    assert compressed.status_code == 200
    assert compressed.headers["content-encoding"] == "gzip"
    assert rejected.status_code == 400


def test_brotli_is_preferred_with_gzip_fallback(
    test_settings: Settings,
) -> None:
    application = create_application(test_settings)

    @application.get("/_test/compression", include_in_schema=False)
    async def compressed_response() -> dict[str, str]:
        return {"content": "compressible " * 200}

    with TestClient(application) as client:
        brotli_response = client.get(
            "/_test/compression",
            headers={"Accept-Encoding": "br, gzip"},
        )

    fallback_settings = test_settings.model_copy(update={"brotli_enabled": False})
    fallback_application = create_application(fallback_settings)

    @fallback_application.get("/_test/compression", include_in_schema=False)
    async def fallback_response() -> dict[str, str]:
        return {"content": "compressible " * 200}

    with TestClient(fallback_application) as client:
        gzip_response = client.get(
            "/_test/compression",
            headers={"Accept-Encoding": "br, gzip"},
        )

    assert brotli_response.headers["Content-Encoding"] == "br"
    assert gzip_response.headers["Content-Encoding"] == "gzip"


def test_hsts_is_production_only() -> None:
    production_headers = build_security_headers(Environment.PRODUCTION)
    development_headers = build_security_headers(Environment.DEVELOPMENT)

    assert "Strict-Transport-Security" in production_headers
    assert "Strict-Transport-Security" not in development_headers
