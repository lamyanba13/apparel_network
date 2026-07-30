from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_reports_ok() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_development_swagger_is_available_without_a_root_route() -> None:
    client = TestClient(app)

    assert client.get("/").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
