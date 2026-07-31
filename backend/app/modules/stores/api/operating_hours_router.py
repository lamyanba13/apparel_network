from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response, status

from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.stores.api.dependencies import StoreOperatingHoursServiceDependency
from app.modules.stores.api.operating_hours_schemas import (
    OperatingIntervalResponse,
    StoreHoursCreateRequest,
    StoreHoursListResponse,
    StoreHoursResponse,
    StoreHoursUpdateRequest,
    StoreScheduleResponse,
    StoreStatusResponse,
)
from app.modules.stores.application.operating_hours_schemas import (
    StoreHoursCreate,
    StoreHoursUpdate,
)
from app.modules.stores.domain.operating_hours import (
    BusinessStatus,
    StoreOperatingHours,
    StoreSchedule,
)

router = APIRouter(
    prefix="/stores/{store_id}",
    tags=["Store Operating Hours"],
)

_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Store permission"},
}
_RESOURCE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_AUTH_RESPONSES,
    404: {"description": "Store or schedule not found"},
}
_MUTATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_RESOURCE_RESPONSES,
    409: {
        "description": (
            "Schedule interval/effective-range conflict or optimistic version conflict"
        )
    },
    422: {"description": "Store schedule validation failed"},
}


def _hours_response(value: StoreOperatingHours) -> StoreHoursResponse:
    return StoreHoursResponse(
        id=value.id,
        store_id=value.store_id,
        day_of_week=value.day_of_week,
        timezone=value.timezone,
        opening_time=value.opening_time,
        closing_time=value.closing_time,
        is_closed=value.is_closed,
        is_24_hours=value.is_24_hours,
        effective_from=value.effective_from,
        effective_until=value.effective_until,
        priority=value.priority,
        notes=value.notes,
        created_at=value.created_at,
        updated_at=value.updated_at,
        version=value.version,
    )


def _schedule_response(value: StoreSchedule) -> StoreScheduleResponse:
    return StoreScheduleResponse(
        store_id=value.store_id,
        day_of_week=value.day_of_week,
        timezone=value.timezone,
        priority=value.priority,
        intervals=[_hours_response(item) for item in value.intervals],
        temporary_override=value.is_temporary_override,
    )


def _status_response(value: BusinessStatus) -> StoreStatusResponse:
    interval = value.current_interval
    return StoreStatusResponse(
        store_id=value.store_id,
        timezone=value.timezone,
        current_status=value.current_status,
        open_now=value.open_now,
        is_24_hours=value.is_24_hours,
        current_interval=(
            OperatingIntervalResponse(
                opening_time=interval.opening_time,
                closing_time=interval.closing_time,
            )
            if interval is not None
            else None
        ),
        today_schedule=(
            _schedule_response(value.today_schedule)
            if value.today_schedule is not None
            else None
        ),
        next_opening=value.next_opening,
        next_closing=value.next_closing,
        temporary_override=value.temporary_override,
    )


@router.post(
    "/hours",
    response_model=StoreHoursResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Store operating-hours interval",
    description=(
        "Creates an owner-scoped recurring interval or temporary override. "
        "Uses store:update and rejects overlapping intervals at equal priority."
    ),
    dependencies=[require_permission("store:update")],
    responses=_MUTATION_RESPONSES,
)
async def create_store_hours(
    store_id: UUID,
    payload: StoreHoursCreateRequest,
    identity: CurrentIdentity,
    service: StoreOperatingHoursServiceDependency,
    response: Response,
) -> StoreHoursResponse:
    schedule = await service.create(
        store_id,
        identity.user.id,
        StoreHoursCreate(
            day_of_week=payload.day_of_week,
            timezone=payload.timezone,
            opening_time=payload.opening_time,
            closing_time=payload.closing_time,
            is_closed=payload.is_closed,
            is_24_hours=payload.is_24_hours,
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
            priority=payload.priority,
            notes=payload.notes,
        ),
    )
    response.headers["Location"] = f"/api/v1/stores/{store_id}/hours/{schedule.id}"
    return _hours_response(schedule)


@router.get(
    "/hours",
    response_model=StoreHoursListResponse,
    summary="List Store operating-hours rules",
    description=(
        "Returns all non-deleted recurring and temporary Store schedule rules, "
        "including retained expired overrides."
    ),
    dependencies=[require_permission("store:view")],
    responses=_RESOURCE_RESPONSES,
)
async def list_store_hours(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreOperatingHoursServiceDependency,
) -> StoreHoursListResponse:
    values = await service.list(store_id, identity.user.id)
    return StoreHoursListResponse(items=[_hours_response(value) for value in values])


@router.get(
    "/hours/today",
    response_model=StoreScheduleResponse | None,
    summary="Get today's resolved Store schedule",
    description=(
        "Resolves the current local weekday, effective ranges, temporary "
        "overrides, and highest active priority."
    ),
    dependencies=[require_permission("store:view")],
    responses=_RESOURCE_RESPONSES,
)
async def get_today_store_hours(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreOperatingHoursServiceDependency,
) -> StoreScheduleResponse | None:
    value = await service.today(store_id, identity.user.id)
    return _schedule_response(value) if value is not None else None


@router.patch(
    "/hours/{schedule_id}",
    response_model=StoreHoursResponse,
    summary="Update a Store operating-hours rule",
    description=(
        "Updates a schedule through optimistic locking and revalidates Store "
        "timezone, interval, effective-range, and priority invariants."
    ),
    dependencies=[require_permission("store:update")],
    responses=_MUTATION_RESPONSES,
)
async def update_store_hours(
    store_id: UUID,
    schedule_id: UUID,
    payload: StoreHoursUpdateRequest,
    identity: CurrentIdentity,
    service: StoreOperatingHoursServiceDependency,
) -> StoreHoursResponse:
    values = payload.model_dump(exclude={"version"}, exclude_unset=True)
    return _hours_response(
        await service.update(
            store_id,
            schedule_id,
            identity.user.id,
            StoreHoursUpdate(expected_version=payload.version, values=values),
        )
    )


@router.delete(
    "/hours/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Store operating-hours rule",
    description="Soft-deletes one owner-scoped schedule rule.",
    dependencies=[require_permission("store:update")],
    responses=_MUTATION_RESPONSES,
)
async def delete_store_hours(
    store_id: UUID,
    schedule_id: UUID,
    identity: CurrentIdentity,
    service: StoreOperatingHoursServiceDependency,
) -> Response:
    await service.delete(store_id, schedule_id, identity.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/status",
    response_model=StoreStatusResponse,
    summary="Get current Store business status",
    description=(
        "Calculates open/closed state, current interval, today's resolved "
        "schedule, and next opening and closing in the Store timezone."
    ),
    dependencies=[require_permission("store:view")],
    responses=_RESOURCE_RESPONSES,
)
async def get_store_status(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreOperatingHoursServiceDependency,
) -> StoreStatusResponse:
    return _status_response(await service.status(store_id, identity.user.id))
