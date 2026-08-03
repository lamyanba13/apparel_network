from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.inventory.api.dependencies import InventoryServiceDependency
from app.modules.inventory.api.schemas import (
    InventoryCreateRequest,
    InventoryListResponse,
    InventoryResponse,
    InventoryUpdateRequest,
)
from app.modules.inventory.application.schemas import InventoryCreate, InventoryUpdate
from app.modules.inventory.domain import InventoryStatus

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
