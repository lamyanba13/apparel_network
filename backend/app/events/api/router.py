from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.common.errors import ErrorCode
from app.common.exceptions import AppError
from app.events.api.dependencies import OutboxOperationsDependency
from app.events.api.schemas import OutboxEventListResponse, OutboxEventResponse
from app.modules.identity.api.authorization import require_permission

router = APIRouter(prefix="/admin/events", tags=["Event Operations"])


@router.get(
    "",
    response_model=OutboxEventListResponse,
    dependencies=[require_permission("admin:access")],
)
async def inspect_events(
    service: OutboxOperationsDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> OutboxEventListResponse:
    return OutboxEventListResponse(
        items=[
            OutboxEventResponse.model_validate(value)
            for value in await service.inspect(limit=limit)
        ]
    )


@router.post(
    "/{event_id}/recover",
    response_model=OutboxEventResponse,
    dependencies=[require_permission("admin:access")],
    responses={404: {"description": "Recoverable event not found"}},
)
async def recover_event(
    event_id: UUID, service: OutboxOperationsDependency
) -> OutboxEventResponse:
    recovered = await service.recover(event_id)
    if recovered is None:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            title="Recoverable event not found",
            detail="The event is not failed or stale.",
            status_code=404,
        )
    return OutboxEventResponse.model_validate(recovered)
