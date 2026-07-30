from typing import Annotated, Literal, TypedDict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.health import check_database_session
from app.database.session import get_db

router = APIRouter()


class HealthResponse(TypedDict):
    status: Literal["ok"]
    database: Literal["healthy"]


@router.get("/health", response_model=None)
async def health(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> HealthResponse:
    """Report API readiness including authoritative database reachability."""
    if not await check_database_session(session):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database dependency is unavailable.",
        )
    return {"status": "ok", "database": "healthy"}
