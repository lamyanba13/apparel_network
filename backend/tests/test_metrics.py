from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_application


def test_metrics_endpoint_exposes_http_and_foundation_metrics(
    test_settings: Settings,
) -> None:
    with TestClient(create_application(test_settings)) as client:
        client.get("/health/live")
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=")
    body = response.text
    assert "fashion_network_http_requests_total" in body
    assert "fashion_network_http_request_duration_seconds" in body
    assert "fashion_network_database_pool_size" in body
    assert "fashion_network_dependency_up" in body
    assert "fashion_network_worker_up" in body
    assert "fashion_network_authentication_succeeded_total" in body
    assert "fashion_network_authentication_failed_total" in body
    assert "fashion_network_authentication_refresh_total" in body
    assert "fashion_network_authentication_refresh_reuse_total" in body
    assert "fashion_network_authentication_logout_total" in body


def test_metrics_endpoint_can_be_disabled(test_settings: Settings) -> None:
    settings = test_settings.model_copy(update={"metrics_enabled": False})
    with TestClient(create_application(settings)) as client:
        response = client.get("/metrics")

    assert response.status_code == 404
