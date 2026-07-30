from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from sqlalchemy.ext.asyncio import AsyncEngine

from app.common.config import Settings

_provider_configured = False
_httpx_instrumented = False
_celery_instrumented = False


@dataclass(frozen=True)
class TelemetryConfiguration:
    enabled: bool
    service_name: str
    environment: str
    release: str
    endpoint: str | None
    sample_ratio: float


def telemetry_configuration(settings: Settings) -> TelemetryConfiguration:
    return TelemetryConfiguration(
        enabled=settings.opentelemetry_enabled,
        service_name=settings.opentelemetry_service_name,
        environment=settings.environment.value,
        release=settings.application_version,
        endpoint=settings.opentelemetry_exporter_otlp_endpoint,
        sample_ratio=settings.opentelemetry_trace_sample_ratio,
    )


def _configure_provider(settings: Settings) -> None:
    global _provider_configured
    if _provider_configured:
        return
    config = telemetry_configuration(settings)
    provider = TracerProvider(
        resource=Resource.create(
            {
                SERVICE_NAME: config.service_name,
                SERVICE_VERSION: config.release,
                DEPLOYMENT_ENVIRONMENT: config.environment,
            }
        ),
        sampler=ParentBased(TraceIdRatioBased(config.sample_ratio)),
    )
    if config.endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=config.endpoint))
        )
    trace.set_tracer_provider(provider)
    _provider_configured = True


def configure_fastapi_telemetry(application: FastAPI, settings: Settings) -> bool:
    """Instrument inbound and outbound HTTP without requiring an exporter."""
    global _httpx_instrumented
    if not settings.opentelemetry_enabled:
        return False
    _configure_provider(settings)
    FastAPIInstrumentor.instrument_app(
        application,
        excluded_urls="health/live,health/startup,metrics",
    )
    if not _httpx_instrumented:
        HTTPXClientInstrumentor().instrument()
        _httpx_instrumented = True
    return True


def configure_sqlalchemy_telemetry(
    engine: AsyncEngine,
    settings: Settings,
) -> bool:
    if not settings.opentelemetry_enabled:
        return False
    _configure_provider(settings)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    return True


def configure_celery_telemetry(settings: Settings) -> bool:
    global _celery_instrumented
    if not settings.opentelemetry_enabled or _celery_instrumented:
        return False
    _configure_provider(settings)
    CeleryInstrumentor().instrument()  # type: ignore[no-untyped-call]
    _celery_instrumented = True
    return True
