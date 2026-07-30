from __future__ import annotations

import sentry_sdk
from sentry_sdk.types import Event, Hint

from app.common.config import Settings

_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-csrf-token",
}


def _scrub_event(event: Event, _hint: Hint) -> Event:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for name in tuple(headers):
                if name.lower() in _SENSITIVE_HEADERS:
                    headers.pop(name, None)
    return event


def configure_sentry(settings: Settings) -> bool:
    """Initialize privacy-safe error capture when explicitly enabled."""
    if not settings.sentry_enabled or settings.sentry_dsn is None:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment.value,
        release=settings.application_version,
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=settings.sentry_trace_sample_rate,
        before_send=_scrub_event,
    )
    return True


def capture_exception(error: BaseException) -> None:
    """Capture a failure when Sentry is active; remain safe when disabled."""
    sentry_sdk.capture_exception(error)
