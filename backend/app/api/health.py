from typing import Literal, TypedDict

from fastapi import APIRouter

router = APIRouter()


class HealthResponse(TypedDict):
    status: Literal["ok"]


@router.get("/health", response_model=None)
def health() -> HealthResponse:
    """Report process liveness for the Phase 1.1 foundation."""
    return {"status": "ok"}
