from collections.abc import Mapping
from typing import Protocol

from pydantic import JsonValue


class ErrorReporter(Protocol):
    """Disabled-by-default seam for a future Sentry adapter."""

    def capture_exception(
        self,
        error: BaseException,
        *,
        context: Mapping[str, JsonValue] | None = None,
    ) -> None: ...


class MetricsRecorder(Protocol):
    """Disabled-by-default seam for future Prometheus/OpenTelemetry metrics."""

    def increment(
        self,
        name: str,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> None: ...

    def observe(
        self,
        name: str,
        value: float,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> None: ...


class TelemetryProvider(Protocol):
    """Lifecycle seam for a future OpenTelemetry provider adapter."""

    def initialize(self) -> None: ...

    def shutdown(self) -> None: ...
