from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.common.config import Settings
from app.common.context import maybe_get_request_context
from app.common.enums import Environment

_STANDARD_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)
_SAFE_EXTRA_FIELDS = frozenset(
    {
        "accepted",
        "accounts_unlocked",
        "actor_user_id",
        "duration_ms",
        "dependency",
        "event",
        "event_correlation_id",
        "event_id",
        "event_occurred_at",
        "expired_sessions",
        "expired_sessions_revoked",
        "family_id",
        "http_method",
        "http_path",
        "operation",
        "permission_name",
        "reason",
        "requirement",
        "reset_tokens_deleted",
        "revoked_sessions",
        "risk_score",
        "role_name",
        "rotation_count",
        "schema_version",
        "session_id",
        "sessions_deleted",
        "status_code",
        "user_id",
        "verification_tokens_deleted",
        "violation_codes",
    }
)


class ApplicationContextFilter(logging.Filter):
    """Attach process and request metadata to every emitted record."""

    def __init__(self, *, environment: Environment, application_version: str) -> None:
        super().__init__()
        self.environment = environment.value
        self.application_version = application_version

    def filter(self, record: logging.LogRecord) -> bool:
        context = maybe_get_request_context()
        record.request_id = str(context.request_id) if context else None
        record.correlation_id = str(context.correlation_id) if context else None
        record.environment = self.environment
        record.application_version = self.application_version
        return True


class JsonFormatter(logging.Formatter):
    """Format one safe, structured JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "request_id": getattr(record, "request_id", None),
            "correlation_id": getattr(record, "correlation_id", None),
            "module": record.name,
            "message": record.getMessage(),
            "environment": getattr(record, "environment", None),
            "application_version": getattr(record, "application_version", None),
        }
        for field in _SAFE_EXTRA_FIELDS:
            if field not in _STANDARD_LOG_RECORD_FIELDS and hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


class PrettyFormatter(logging.Formatter):
    """Readable local logs that retain the required correlation metadata."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        request_id = getattr(record, "request_id", None) or "-"
        correlation_id = getattr(record, "correlation_id", None) or "-"
        environment = getattr(record, "environment", None) or "-"
        version = getattr(record, "application_version", None) or "-"
        return (
            f"{timestamp} {record.levelname:<8} {record.name} "
            f"request_id={request_id} correlation_id={correlation_id} "
            f"environment={environment} version={version} {record.getMessage()}"
        )


def configure_logging(settings: Settings) -> None:
    """Configure one process-wide, secret-safe logging pipeline."""
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(
        ApplicationContextFilter(
            environment=settings.environment,
            application_version=settings.application_version,
        )
    )
    if settings.environment is Environment.PRODUCTION:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(PrettyFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        framework_logger = logging.getLogger(logger_name)
        framework_logger.handlers.clear()
        framework_logger.propagate = True
