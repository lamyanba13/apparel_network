import json
import logging
from typing import cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.common.context import RequestContext, bind_request_context, get_request_context
from app.common.enums import Environment
from app.common.logging.configuration import (
    ApplicationContextFilter,
    JsonFormatter,
)
from app.common.middleware import logging as request_logging
from app.common.utils import utc_now
from app.core.config import Settings
from app.main import create_application


def test_json_logging_contains_required_process_and_request_context() -> None:
    context = RequestContext(
        request_id=uuid4(),
        correlation_id=uuid4(),
        started_at=utc_now(),
        client_ip="127.0.0.1",
        user_agent="pytest",
    )
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="foundation.ready",
        args=(),
        exc_info=None,
    )
    context_filter = ApplicationContextFilter(
        environment=Environment.PRODUCTION,
        application_version="1.2.3",
    )

    with bind_request_context(context):
        assert context_filter.filter(record)
        payload = json.loads(JsonFormatter().format(record))

    assert payload == {
        "timestamp": payload["timestamp"],
        "level": "info",
        "request_id": str(context.request_id),
        "correlation_id": str(context.correlation_id),
        "module": "app.test",
        "message": "foundation.ready",
        "environment": "production",
        "application_version": "1.2.3",
    }


def test_json_logging_allows_auditable_identity_fields_and_drops_secrets() -> None:
    record = logging.LogRecord(
        name="app.modules.identity",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="identity.refresh_reuse_detected",
        args=(),
        exc_info=None,
    )
    event_id = str(uuid4())
    user_id = str(uuid4())
    session_id = str(uuid4())
    record.__dict__.update(
        {
            "event": "identity.refresh_reuse_detected",
            "event_id": event_id,
            "event_occurred_at": utc_now().isoformat(),
            "user_id": user_id,
            "session_id": session_id,
            "reason": "refresh_reuse",
            "password": "must-not-appear",
            "refresh_token": "must-not-appear",
            "email": "must-not-appear@example.com",
        }
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "identity.refresh_reuse_detected"
    assert payload["event_id"] == event_id
    assert payload["user_id"] == user_id
    assert payload["session_id"] == session_id
    assert payload["reason"] == "refresh_reuse"
    assert "password" not in payload
    assert "refresh_token" not in payload
    assert "email" not in payload


def test_request_logging_middleware_includes_request_identifiers(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def capture_log(message: str, *, extra: dict[str, object]) -> None:
        context = get_request_context()
        captured.update(
            {
                "message": message,
                "extra": extra,
                "request_id": str(context.request_id),
                "correlation_id": str(context.correlation_id),
            }
        )

    monkeypatch.setattr(request_logging.logger, "info", capture_log)

    with TestClient(create_application(test_settings)) as client:
        response = client.get("/health/live")

    assert captured["message"] == "http.request_completed"
    assert captured["request_id"] == response.headers["X-Request-ID"]
    assert captured["correlation_id"] == response.headers["X-Correlation-ID"]
    extra = cast(dict[str, object], captured["extra"])
    assert extra["event"] == "http.request_completed"
    assert extra["http_method"] == "GET"
    assert extra["http_path"] == "/health/live"
    assert extra["status_code"] == 200
    assert isinstance(extra["duration_ms"], float)
