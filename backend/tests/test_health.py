from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_application


def test_health_endpoint_reports_database_readiness(
    test_settings: Settings,
) -> None:
    with TestClient(create_application(test_settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "healthy"}


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
    health_parameters = schema["paths"]["/health"]["get"]["parameters"]
    assert any(parameter["name"] == "X-Request-ID" for parameter in health_parameters)
    assert not any(path.startswith("/api/v1/") for path in schema["paths"])
