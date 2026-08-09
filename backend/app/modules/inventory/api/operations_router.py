from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query

from app.common.pagination import PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.inventory.api.dependencies import RetailerOperationsDependency
from app.modules.inventory.api.schemas import (
    RetailerOperationsSummaryResponse,
    RetailerOrderActivityListResponse,
    RetailerOrderActivityResponse,
    RetailerShipmentActivityListResponse,
    RetailerShipmentActivityResponse,
)
from app.modules.inventory.application.schemas import RetailerActivityFilter
from app.modules.orders.domain import OrderStatus
from app.modules.shipments.domain import ShipmentStatus

router = APIRouter(prefix="/retailer/operations", tags=["Retailer Operations"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Inventory permission"},
    404: {"description": "Store not found or inaccessible to this identity"},
}


@router.get(
    "/summary",
    response_model=RetailerOperationsSummaryResponse,
    dependencies=[require_permission("inventory:view")],
    responses=_RESPONSES,
)
async def operations_summary(
    store_id: UUID,
    identity: CurrentIdentity,
    service: RetailerOperationsDependency,
) -> RetailerOperationsSummaryResponse:
    return RetailerOperationsSummaryResponse.model_validate(
        await service.summary(store_id, identity.user.id)
    )


@router.get(
    "/orders",
    response_model=RetailerOrderActivityListResponse,
    dependencies=[require_permission("inventory:view")],
    responses=_RESPONSES,
)
async def operational_orders(
    store_id: UUID,
    identity: CurrentIdentity,
    service: RetailerOperationsDependency,
    status: OrderStatus | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> RetailerOrderActivityListResponse:
    values, total = await service.orders(
        identity.user.id,
        RetailerActivityFilter(
            store_id=store_id,
            status=status.value if status else None,
            offset=offset,
            limit=limit,
        ),
    )
    return RetailerOrderActivityListResponse(
        items=[RetailerOrderActivityResponse.model_validate(value) for value in values],
        page=PageMetadata(
            has_more=offset + len(values) < total,
            limit=limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/shipments",
    response_model=RetailerShipmentActivityListResponse,
    dependencies=[require_permission("inventory:view")],
    responses=_RESPONSES,
)
async def operational_shipments(
    store_id: UUID,
    identity: CurrentIdentity,
    service: RetailerOperationsDependency,
    status: ShipmentStatus | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> RetailerShipmentActivityListResponse:
    values, total = await service.shipments(
        identity.user.id,
        RetailerActivityFilter(
            store_id=store_id,
            status=status.value if status else None,
            offset=offset,
            limit=limit,
        ),
    )
    return RetailerShipmentActivityListResponse(
        items=[
            RetailerShipmentActivityResponse.model_validate(value) for value in values
        ],
        page=PageMetadata(
            has_more=offset + len(values) < total,
            limit=limit,
            total=total,
            offset=offset,
        ),
    )
