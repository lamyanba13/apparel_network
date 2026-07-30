from collections.abc import Awaitable, Callable

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.health import HealthService
from app.main import create_application


async def _healthy() -> bool:
    return True


async def _unhealthy() -> bool:
    return False


def _health_service(
    check: Callable[[], Awaitable[bool]] = _healthy,
) -> HealthService:
    service = HealthService(
        checks={
            "postgresql": check,
            "rabbitmq": check,
            "redis": check,
            "meilisearch": check,
            "minio": check,
        },
        timeout_seconds=0.1,
    )
    service.startup_complete = True
    return service


def test_liveness_checks_only_the_application_process(
    test_settings: Settings,
) -> None:
    with TestClient(create_application(test_settings)) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "alive",
        "service": "fashion-network-api",
        "version": "0.1.0",
    }


def test_readiness_reports_all_required_dependencies(
    test_settings: Settings,
) -> None:
    application = create_application(test_settings)
    with TestClient(application) as client:
        application.state.health = _health_service()
        response = client.get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert set(payload["checks"]) == {
        "postgresql",
        "rabbitmq",
        "redis",
        "meilisearch",
        "minio",
    }
    assert all(result["status"] == "healthy" for result in payload["checks"].values())


def test_readiness_returns_503_when_a_dependency_is_unavailable(
    test_settings: Settings,
) -> None:
    application = create_application(test_settings)
    with TestClient(application) as client:
        application.state.health = _health_service(_unhealthy)
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_startup_probe_reports_completed_lifespan(
    test_settings: Settings,
) -> None:
    with TestClient(create_application(test_settings)) as client:
        response = client.get("/health/startup")

    assert response.status_code == 200
    assert response.json() == {"status": "started"}


def test_legacy_health_endpoint_is_removed(test_settings: Settings) -> None:
    with TestClient(create_application(test_settings)) as client:
        response = client.get("/health")

    assert response.status_code == 404


def test_development_swagger_is_available_without_a_root_route(
    test_settings: Settings,
) -> None:
    with TestClient(create_application(test_settings)) as client:
        assert client.get("/").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/docs").status_code == 200
        openapi_response = client.get("/openapi.json")

    assert openapi_response.status_code == 200
    schema = openapi_response.json()
    assert schema["info"]["title"] == "Fashion Network API"
    assert schema["info"]["contact"]["name"] == "Fashion Network Engineering"
    assert schema["info"]["license"]["name"] == "Proprietary"
    live_parameters = schema["paths"]["/health/live"]["get"]["parameters"]
    assert any(parameter["name"] == "X-Request-ID" for parameter in live_parameters)
    assert "/metrics" not in schema["paths"]
    assert {
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/logout-all",
    } <= set(schema["paths"])
