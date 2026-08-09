from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.inventory.api.dependencies import InventoryServiceDependency
from app.modules.inventory.api.schemas import (
    InventoryAdjustmentRequest,
    InventoryCreateRequest,
    InventoryListResponse,
    InventoryMovementListResponse,
    InventoryMovementResponse,
    InventoryReconciliationRequest,
    InventoryResponse,
    InventoryStockListResponse,
    InventoryStockResponse,
    InventoryUpdateRequest,
)
from app.modules.inventory.application.schemas import (
    InventoryAdjustment,
    InventoryCreate,
    InventoryMovementFilter,
    InventoryReconciliation,
    InventoryStockFilter,
    InventoryUpdate,
)
from app.modules.inventory.domain import (
    InventoryMovementType,
    InventoryStatus,
    StockClassification,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Catalog permission"},
    404: {"description": "Inventory not found or not owned by this identity"},
}


def _response(item: Any) -> InventoryResponse:
    return InventoryResponse.model_validate(item, from_attributes=True)


@router.post(
    "",
    response_model=InventoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Variant inventory already exists"}},
)
async def create_inventory(
    payload: InventoryCreateRequest,
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
    response: Response,
) -> InventoryResponse:
    item = await service.create(
        InventoryCreate(
            payload.variant_id,
            payload.quantity_on_hand,
            payload.quantity_reserved,
            payload.status,
            payload.tracking_policy,
            payload.low_stock_threshold,
            identity.user.id,
        )
    )
    response.headers["Location"] = f"/api/v1/inventory/{item.id}"
    return _response(item)


@router.get(
    "",
    response_model=InventoryListResponse,
    dependencies=[require_permission("catalog:view")],
    responses=_RESPONSES,
)
async def list_inventory(
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
    store_id: UUID | None = None,
    catalog_id: UUID | None = None,
    product_id: UUID | None = None,
    variant_id: UUID | None = None,
    status_filter: Annotated[InventoryStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> InventoryListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    items, total = await service.list_owned(
        identity.user.id,
        store_id=store_id,
        catalog_id=catalog_id,
        product_id=product_id,
        variant_id=variant_id,
        status=status_filter,
        offset=offset,
        limit=limit,
    )
    return InventoryListResponse(
        items=[_response(item) for item in items],
        page=PageMetadata(
            has_more=offset + len(items) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


async def _movement_page(
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
    *,
    store_id: UUID | None,
    inventory_id: UUID | None,
    variant_id: UUID | None,
    movement_type: InventoryMovementType | None,
    created_from: datetime | None,
    created_to: datetime | None,
    actor_id: UUID | None,
    source: str | None,
    reference_id: UUID | None,
    offset: int,
    limit: int,
) -> InventoryMovementListResponse:
    values, total = await service.movement_history(
        identity.user.id,
        InventoryMovementFilter(
            store_id,
            inventory_id,
            variant_id,
            movement_type,
            created_from,
            created_to,
            actor_id,
            source,
            reference_id,
            offset,
            limit,
        ),
    )
    return InventoryMovementListResponse(
        items=[InventoryMovementResponse.model_validate(value) for value in values],
        page=PageMetadata(
            has_more=offset + len(values) < total,
            limit=limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/movements",
    response_model=InventoryMovementListResponse,
    dependencies=[require_permission("inventory:view")],
    responses=_RESPONSES,
)
async def list_inventory_movements(
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
    store_id: UUID | None = None,
    inventory_id: UUID | None = None,
    variant_id: UUID | None = None,
    movement_type: InventoryMovementType | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    actor_id: UUID | None = None,
    source: str | None = None,
    reference_id: UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> InventoryMovementListResponse:
    return await _movement_page(
        identity,
        service,
        store_id=store_id,
        inventory_id=inventory_id,
        variant_id=variant_id,
        movement_type=movement_type,
        created_from=created_from,
        created_to=created_to,
        actor_id=actor_id,
        source=source,
        reference_id=reference_id,
        offset=offset,
        limit=limit,
    )


async def _stock_page(
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
    classification: StockClassification,
    store_id: UUID | None,
    offset: int,
    limit: int,
) -> InventoryStockListResponse:
    values, total = await service.stock_by_classification(
        identity.user.id,
        InventoryStockFilter(classification, store_id, offset, limit),
    )
    return InventoryStockListResponse(
        items=[
            InventoryStockResponse(
                inventory=_response(value.inventory),
                active_reservation_quantity=value.active_reservation_quantity,
                effective_available=value.effective_available,
                classification=value.classification,
            )
            for value in values
        ],
        page=PageMetadata(
            has_more=offset + len(values) < total,
            limit=limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/low-stock",
    response_model=InventoryStockListResponse,
    dependencies=[require_permission("inventory:view")],
    responses=_RESPONSES,
)
async def list_low_stock(
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
    store_id: UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> InventoryStockListResponse:
    return await _stock_page(
        identity,
        service,
        StockClassification.LOW_STOCK,
        store_id,
        offset,
        limit,
    )


@router.get(
    "/out-of-stock",
    response_model=InventoryStockListResponse,
    dependencies=[require_permission("inventory:view")],
    responses=_RESPONSES,
)
async def list_out_of_stock(
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
    store_id: UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> InventoryStockListResponse:
    return await _stock_page(
        identity,
        service,
        StockClassification.OUT_OF_STOCK,
        store_id,
        offset,
        limit,
    )


@router.get(
    "/{inventory_id}",
    response_model=InventoryResponse,
    dependencies=[require_permission("catalog:view")],
    responses=_RESPONSES,
)
async def get_inventory(
    inventory_id: UUID, identity: CurrentIdentity, service: InventoryServiceDependency
) -> InventoryResponse:
    return _response(await service.get_owned(inventory_id, identity.user.id))


@router.post(
    "/{inventory_id}/adjust",
    response_model=InventoryResponse,
    dependencies=[require_permission("inventory:update")],
    responses={**_RESPONSES, 409: {"description": "Inventory adjustment conflict"}},
)
async def adjust_inventory(
    inventory_id: UUID,
    payload: InventoryAdjustmentRequest,
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
) -> InventoryResponse:
    return _response(
        await service.adjust_owned(
            inventory_id,
            identity.user.id,
            InventoryAdjustment(
                quantity_delta=payload.quantity_delta,
                movement_type=payload.movement_type,
                reason=payload.reason,
                expected_version=payload.version,
                actor_id=identity.user.id,
                source=payload.source,
                reference_id=payload.reference_id,
            ),
        )
    )


@router.post(
    "/{inventory_id}/reconcile",
    response_model=InventoryResponse,
    dependencies=[require_permission("inventory:update")],
    responses={**_RESPONSES, 409: {"description": "Inventory reconciliation conflict"}},
)
async def reconcile_inventory(
    inventory_id: UUID,
    payload: InventoryReconciliationRequest,
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
) -> InventoryResponse:
    return _response(
        await service.reconcile_owned(
            inventory_id,
            identity.user.id,
            InventoryReconciliation(
                physical_count=payload.physical_count,
                reason=payload.reason,
                expected_version=payload.version,
                actor_id=identity.user.id,
                source=payload.source,
                reference_id=payload.reference_id,
            ),
        )
    )


@router.get(
    "/{inventory_id}/movements",
    response_model=InventoryMovementListResponse,
    dependencies=[require_permission("inventory:view")],
    responses=_RESPONSES,
)
async def list_item_movements(
    inventory_id: UUID,
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
    movement_type: InventoryMovementType | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    actor_id: UUID | None = None,
    source: str | None = None,
    reference_id: UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> InventoryMovementListResponse:
    await service.get_owned(inventory_id, identity.user.id)
    return await _movement_page(
        identity,
        service,
        store_id=None,
        inventory_id=inventory_id,
        variant_id=None,
        movement_type=movement_type,
        created_from=created_from,
        created_to=created_to,
        actor_id=actor_id,
        source=source,
        reference_id=reference_id,
        offset=offset,
        limit=limit,
    )


@router.patch(
    "/{inventory_id}",
    response_model=InventoryResponse,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def update_inventory(
    inventory_id: UUID,
    payload: InventoryUpdateRequest,
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
) -> InventoryResponse:
    return _response(
        await service.update_owned(
            inventory_id,
            identity.user.id,
            InventoryUpdate(
                payload.model_dump(exclude={"version"}, exclude_unset=True),
                payload.version,
                identity.user.id,
            ),
        )
    )


@router.delete(
    "/{inventory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def delete_inventory(
    inventory_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: InventoryServiceDependency,
) -> Response:
    await service.delete_owned(inventory_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
