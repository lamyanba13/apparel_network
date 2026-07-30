from __future__ import annotations

from typing import Literal, TypedDict, cast

from fastapi import APIRouter, Request, Response, status

from app.core.config import Settings
from app.health import HealthService

router = APIRouter(prefix="/health", tags=["health"])


class ProcessHealthResponse(TypedDict):
    status: Literal["alive"]
    service: str
    version: str


class StartupHealthResponse(TypedDict):
    status: Literal["started", "starting"]


def _health_service(request: Request) -> HealthService:
    return cast(HealthService, request.app.state.health)


@router.get("/live", response_model=None)
async def live(request: Request) -> ProcessHealthResponse:
    """Confirm that the application process can serve HTTP."""
    settings = cast(Settings, request.app.state.settings)
    return {
        "status": "alive",
        "service": settings.opentelemetry_service_name,
        "version": settings.application_version,
    }


@router.get("/startup", response_model=None)
async def startup(request: Request, response: Response) -> StartupHealthResponse:
    """Report whether the application startup sequence completed."""
    started = _health_service(request).startup_complete
    if not started:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "started" if started else "starting"}


@router.get("/ready", response_model=None)
async def ready(request: Request, response: Response) -> dict[str, object]:
    """Check every dependency required to serve the backend role."""
    result = await _health_service(request).readiness()
    if result.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": result.status,
        "checks": {
            name: {
                "status": check.status,
                "latency_ms": check.latency_ms,
            }
            for name, check in result.checks.items()
        },
    }
