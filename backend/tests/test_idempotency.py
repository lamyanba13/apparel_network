from typing import Annotated

from fastapi import Depends
from fastapi.testclient import TestClient

from app.common.api import idempotency_key_dependency
from app.common.idempotency import (
    IdempotencyKey,
    build_request_fingerprint,
    parse_idempotency_key,
)
from app.core.config import Settings
from app.main import create_application


def test_idempotency_key_and_fingerprint_are_deterministic() -> None:
    key = parse_idempotency_key("request-01.abcdef")
    first = build_request_fingerprint(
        method="post",
        path="/api/v1/reservations",
        canonical_body=b'{"quantity":1}',
    )
    second = build_request_fingerprint(
        method="POST",
        path="/api/v1/reservations",
        canonical_body=b'{"quantity":1}',
    )

    assert key == IdempotencyKey("request-01.abcdef")
    assert first == second
    assert len(first) == 64


def test_idempotency_dependency_documents_and_validates_header(
    test_settings: Settings,
) -> None:
    application = create_application(test_settings)

    @application.post("/_test/idempotency", include_in_schema=False)
    async def command(
        key: Annotated[IdempotencyKey, Depends(idempotency_key_dependency)],
    ) -> dict[str, str]:
        return {"key": key.value}

    with TestClient(application) as client:
        accepted = client.post(
            "/_test/idempotency",
            headers={"Idempotency-Key": "request-01.abcdef"},
        )
        invalid = client.post(
            "/_test/idempotency",
            headers={"Idempotency-Key": "short"},
        )
        missing = client.post("/_test/idempotency")

    assert accepted.json() == {"key": "request-01.abcdef"}
    assert invalid.status_code == 422
    assert invalid.json()["errors"][0]["code"] == "invalid_idempotency_key"
    assert missing.status_code == 422
