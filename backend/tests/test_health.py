from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_reports_ok() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_framework_documentation_routes_are_disabled() -> None:
    client = TestClient(app)

    for path in ("/", "/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
