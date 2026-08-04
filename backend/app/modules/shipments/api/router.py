from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.shipments.api.dependencies import ShipmentServiceDependency
from app.modules.shipments.api.schemas import (
    ShipmentCreateRequest,
    ShipmentDetailResponse,
    ShipmentListResponse,
    ShipmentPackageResponse,
    ShipmentPackRequest,
    ShipmentResponse,
    ShipmentTrackingEventResponse,
    ShipmentTrackingResponse,
    ShipmentTransitionRequest,
)
from app.modules.shipments.application.schemas import (
    PackageCreate,
    ShipmentCreate,
    ShipmentFilter,
    ShipmentPack,
    ShipmentTransition,
)
from app.modules.shipments.domain import ShipmentStatus

router = APIRouter(prefix="/shipments", tags=["Shipments"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Shipment permission"},
    404: {"description": "Shipment not found or owned by another customer"},
}


def _shipment(value: Any) -> ShipmentResponse:
    return ShipmentResponse.model_validate(value, from_attributes=True)


@router.post(
    "",
    response_model=ShipmentResponse,
    status_code=201,
    dependencies=[require_permission("shipment:create")],
    responses={**_RESPONSES, 409: {"description": "Shipment creation conflict"}},
)
async def create_shipment(
    payload: ShipmentCreateRequest,
    identity: CurrentIdentity,
    service: ShipmentServiceDependency,
) -> ShipmentResponse:
    return _shipment(
        await service.create(
            ShipmentCreate(
                order_id=payload.order_id,
                reservation_id=payload.reservation_id,
                payment_id=payload.payment_id,
                shipping_method=payload.shipping_method,
                actor_id=identity.user.id,
            )
        )
    )


@router.get(
    "",
    response_model=ShipmentListResponse,
    dependencies=[require_permission("shipment:view")],
    responses=_RESPONSES,
)
async def list_shipments(
    identity: CurrentIdentity,
    service: ShipmentServiceDependency,
    store_id: UUID | None = None,
    order_id: UUID | None = None,
    status_filter: Annotated[ShipmentStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ShipmentListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    values, total = await service.list_owned(
        identity.user.id,
        ShipmentFilter(store_id, order_id, status_filter, offset, limit),
    )
    return ShipmentListResponse(
        items=[_shipment(value) for value in values],
        page=PageMetadata(
            has_more=offset + len(values) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/{shipment_id}",
    response_model=ShipmentDetailResponse,
    dependencies=[require_permission("shipment:view")],
    responses=_RESPONSES,
)
async def get_shipment(
    shipment_id: UUID,
    identity: CurrentIdentity,
    service: ShipmentServiceDependency,
) -> ShipmentDetailResponse:
    shipment, packages, tracking = await service.detail_owned(
        shipment_id, identity.user.id
    )
    return ShipmentDetailResponse(
        **_shipment(shipment).model_dump(),
        packages=[ShipmentPackageResponse.model_validate(value) for value in packages],
        tracking=[
            ShipmentTrackingEventResponse.model_validate(value) for value in tracking
        ],
    )


@router.post(
    "/{shipment_id}/pack",
    response_model=ShipmentResponse,
    dependencies=[require_permission("shipment:update")],
    responses={**_RESPONSES, 409: {"description": "Shipment conflict"}},
)
async def pack_shipment(
    shipment_id: UUID,
    payload: ShipmentPackRequest,
    identity: CurrentIdentity,
    service: ShipmentServiceDependency,
) -> ShipmentResponse:
    return _shipment(
        await service.pack_owned(
            shipment_id,
            identity.user.id,
            ShipmentPack(
                payload.version,
                tuple(PackageCreate(**item.model_dump()) for item in payload.packages),
                identity.user.id,
            ),
        )
    )


async def _transition(
    operation: str,
    shipment_id: UUID,
    payload: ShipmentTransitionRequest,
    identity: CurrentIdentity,
    service: ShipmentServiceDependency,
) -> ShipmentResponse:
    values = ShipmentTransition(payload.version, identity.user.id)
    method = {
        "ship": service.ship_owned,
        "deliver": service.deliver_owned,
        "cancel": service.cancel_owned,
    }[operation]
    return _shipment(await method(shipment_id, identity.user.id, values))


@router.post(
    "/{shipment_id}/ship",
    response_model=ShipmentResponse,
    dependencies=[require_permission("shipment:ship")],
    responses={**_RESPONSES, 409: {"description": "Shipment conflict"}},
)
async def ship_shipment(
    shipment_id: UUID,
    payload: ShipmentTransitionRequest,
    identity: CurrentIdentity,
    service: ShipmentServiceDependency,
) -> ShipmentResponse:
    return await _transition("ship", shipment_id, payload, identity, service)


@router.post(
    "/{shipment_id}/deliver",
    response_model=ShipmentResponse,
    dependencies=[require_permission("shipment:deliver")],
    responses={**_RESPONSES, 409: {"description": "Shipment conflict"}},
)
async def deliver_shipment(
    shipment_id: UUID,
    payload: ShipmentTransitionRequest,
    identity: CurrentIdentity,
    service: ShipmentServiceDependency,
) -> ShipmentResponse:
    return await _transition("deliver", shipment_id, payload, identity, service)


@router.post(
    "/{shipment_id}/cancel",
    response_model=ShipmentResponse,
    dependencies=[require_permission("shipment:update")],
    responses={**_RESPONSES, 409: {"description": "Shipment conflict"}},
)
async def cancel_shipment(
    shipment_id: UUID,
    payload: ShipmentTransitionRequest,
    identity: CurrentIdentity,
    service: ShipmentServiceDependency,
) -> ShipmentResponse:
    return await _transition("cancel", shipment_id, payload, identity, service)


@router.get(
    "/{shipment_id}/tracking",
    response_model=ShipmentTrackingResponse,
    dependencies=[require_permission("shipment:view")],
    responses=_RESPONSES,
)
async def shipment_tracking(
    shipment_id: UUID,
    identity: CurrentIdentity,
    service: ShipmentServiceDependency,
) -> ShipmentTrackingResponse:
    values = await service.tracking_owned(shipment_id, identity.user.id)
    return ShipmentTrackingResponse(
        items=[ShipmentTrackingEventResponse.model_validate(value) for value in values]
    )
