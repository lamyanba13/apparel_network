from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.reservations.api.dependencies import ReservationServiceDependency
from app.modules.reservations.api.schemas import (
    ReservationCreateRequest,
    ReservationDetailResponse,
    ReservationItemResponse,
    ReservationListResponse,
    ReservationResponse,
    ReservationStatusResponse,
    ReservationTransitionRequest,
)
from app.modules.reservations.application.schemas import (
    ReservationCreate,
    ReservationFilter,
    ReservationTransition,
)
from app.modules.reservations.domain import ReservationStatus

router: APIRouter = APIRouter(prefix="/reservations", tags=["Reservations"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Reservation permission"},
    404: {"description": "Reservation not found or owned by another customer"},
}


def _reservation(value: Any) -> ReservationResponse:
    return ReservationResponse.model_validate(value, from_attributes=True)


@router.post(
    "",
    response_model=ReservationResponse,
    status_code=201,
    dependencies=[require_permission("reservation:create")],
    responses={**_RESPONSES, 409: {"description": "Reservation creation conflict"}},
)
async def create_reservation(
    payload: ReservationCreateRequest,
    identity: CurrentIdentity,
    service: ReservationServiceDependency,
) -> ReservationResponse:
    return _reservation(
        await service.create(
            ReservationCreate(
                order_id=payload.order_id,
                payment_id=payload.payment_id,
                actor_id=identity.user.id,
                expires_at=payload.expires_at,
            )
        )
    )


@router.get(
    "",
    response_model=ReservationListResponse,
    dependencies=[require_permission("reservation:view")],
    responses=_RESPONSES,
)
async def list_reservations(
    identity: CurrentIdentity,
    service: ReservationServiceDependency,
    store_id: UUID | None = None,
    order_id: UUID | None = None,
    status_filter: Annotated[ReservationStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ReservationListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    reservations, total = await service.list_owned(
        identity.user.id,
        ReservationFilter(
            store_id=store_id,
            order_id=order_id,
            status=status_filter,
            offset=offset,
            limit=limit,
        ),
    )
    return ReservationListResponse(
        items=[_reservation(value) for value in reservations],
        page=PageMetadata(
            has_more=offset + len(reservations) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/{reservation_id}",
    response_model=ReservationDetailResponse,
    dependencies=[require_permission("reservation:view")],
    responses=_RESPONSES,
)
async def get_reservation(
    reservation_id: UUID,
    identity: CurrentIdentity,
    service: ReservationServiceDependency,
) -> ReservationDetailResponse:
    reservation, items = await service.detail_owned(reservation_id, identity.user.id)
    return ReservationDetailResponse(
        **_reservation(reservation).model_dump(),
        items=[
            ReservationItemResponse.model_validate(value, from_attributes=True)
            for value in items
        ],
    )


@router.post(
    "/{reservation_id}/release",
    response_model=ReservationResponse,
    dependencies=[require_permission("reservation:release")],
    responses={**_RESPONSES, 409: {"description": "Reservation conflict"}},
)
async def release_reservation(
    reservation_id: UUID,
    payload: ReservationTransitionRequest,
    identity: CurrentIdentity,
    service: ReservationServiceDependency,
) -> ReservationResponse:
    return _reservation(
        await service.release_owned(
            reservation_id,
            identity.user.id,
            ReservationTransition(payload.version, identity.user.id),
        )
    )


@router.post(
    "/{reservation_id}/consume",
    response_model=ReservationResponse,
    dependencies=[require_permission("reservation:consume")],
    responses={**_RESPONSES, 409: {"description": "Reservation conflict"}},
)
async def consume_reservation(
    reservation_id: UUID,
    payload: ReservationTransitionRequest,
    identity: CurrentIdentity,
    service: ReservationServiceDependency,
) -> ReservationResponse:
    return _reservation(
        await service.consume_owned(
            reservation_id,
            identity.user.id,
            ReservationTransition(payload.version, identity.user.id),
        )
    )


@router.get(
    "/{reservation_id}/status",
    response_model=ReservationStatusResponse,
    dependencies=[require_permission("reservation:view")],
    responses=_RESPONSES,
)
async def reservation_status(
    reservation_id: UUID,
    identity: CurrentIdentity,
    service: ReservationServiceDependency,
) -> ReservationStatusResponse:
    reservation = await service.get_owned(reservation_id, identity.user.id)
    return ReservationStatusResponse(
        reservation_id=reservation.id,
        status=reservation.status,
        expires_at=reservation.expires_at,
        checked_at=datetime.now(UTC),
    )
