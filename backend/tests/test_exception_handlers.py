from typing import Annotated

from fastapi import HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.main import create_application


class InvalidFoundationValue(BaseModel):
    count: int


def test_request_validation_uses_problem_details(
    test_settings: Settings,
) -> None:
    application = create_application(test_settings)

    @application.get("/_test/validate", include_in_schema=False)
    async def validate_endpoint(
        quantity: Annotated[int, Query(ge=1)],
    ) -> dict[str, int]:
        return {"quantity": quantity}

    with TestClient(application) as client:
        response = client.get("/_test/validate?quantity=0")

    body = response.json()
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert body["code"] == "validation_error"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["errors"][0]["field"] == "query.quantity"


def test_http_exception_uses_stable_problem_code(test_settings: Settings) -> None:
    application = create_application(test_settings)

    @application.get("/_test/conflict", include_in_schema=False)
    async def conflict_endpoint() -> None:
        raise HTTPException(status_code=409, detail="The operation conflicts.")

    with TestClient(application) as client:
        response = client.get("/_test/conflict")

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"
    assert response.json()["detail"] == "The operation conflicts."


def test_pydantic_validation_error_is_centralized(test_settings: Settings) -> None:
    application = create_application(test_settings)

    @application.get("/_test/pydantic-error", include_in_schema=False)
    async def pydantic_error_endpoint() -> None:
        InvalidFoundationValue.model_validate({"count": "invalid"})

    with TestClient(application) as client:
        response = client.get("/_test/pydantic-error")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_database_error_does_not_expose_infrastructure_details(
    test_settings: Settings,
) -> None:
    application = create_application(test_settings)

    @application.get("/_test/database-error", include_in_schema=False)
    async def database_error_endpoint() -> None:
        raise SQLAlchemyError("postgresql://user:secret@private-host")

    with TestClient(application) as client:
        response = client.get("/_test/database-error")

    serialized = response.text
    assert response.status_code == 503
    assert response.json()["code"] == "database_error"
    assert "secret" not in serialized
    assert "private-host" not in serialized


def test_unhandled_error_returns_no_stack_trace(test_settings: Settings) -> None:
    application = create_application(test_settings)

    @application.get("/_test/unhandled", include_in_schema=False)
    async def unhandled_endpoint() -> None:
        raise RuntimeError("sensitive implementation detail")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/_test/unhandled")

    serialized = response.text
    assert response.status_code == 500
    assert response.json()["code"] == "internal_server_error"
    assert response.json()["request_id"] != "unavailable"
    assert "sensitive implementation detail" not in serialized
    assert "traceback" not in serialized.lower()
