from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.products.api.dependencies import ProductServiceDependency
from app.modules.products.api.schemas import (
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductUpdateRequest,
)
from app.modules.products.application.schemas import ProductCreate, ProductUpdate
from app.modules.products.domain import ProductStatus, ProductVisibility

router = APIRouter(prefix="/products", tags=["Products"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Catalog permission"},
    404: {"description": "Product not found or not owned by this identity"},
}


def _response(product: Any) -> ProductResponse:
    return ProductResponse.model_validate(product, from_attributes=True)


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Product uniqueness conflict"}},
)
async def create_product(
    payload: ProductCreateRequest,
    identity: CurrentIdentity,
    service: ProductServiceDependency,
    response: Response,
) -> ProductResponse:
    product = await service.create(
        ProductCreate(
            payload.catalog_id,
            payload.name,
            payload.slug,
            payload.short_description,
            payload.description,
            payload.status,
            payload.visibility,
            payload.sku,
            payload.brand,
            payload.sort_order,
            identity.user.id,
        )
    )
    response.headers["Location"] = f"/api/v1/products/{product.id}"
    return _response(product)


@router.get(
    "",
    response_model=ProductListResponse,
    dependencies=[require_permission("catalog:view")],
    responses=_RESPONSES,
)
async def list_products(
    identity: CurrentIdentity,
    service: ProductServiceDependency,
    catalog_id: UUID | None = None,
    status_filter: Annotated[ProductStatus | None, Query(alias="status")] = None,
    visibility: ProductVisibility | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ProductListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    items, total = await service.list_owned(
        identity.user.id,
        catalog_id=catalog_id,
        status=status_filter,
        visibility=visibility,
        offset=offset,
        limit=limit,
    )
    return ProductListResponse(
        items=[_response(item) for item in items],
        page=PageMetadata(
            has_more=offset + len(items) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    dependencies=[require_permission("catalog:view")],
    responses=_RESPONSES,
)
async def get_product(
    product_id: UUID, identity: CurrentIdentity, service: ProductServiceDependency
) -> ProductResponse:
    return _response(await service.get_owned(product_id, identity.user.id))


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def update_product(
    product_id: UUID,
    payload: ProductUpdateRequest,
    identity: CurrentIdentity,
    service: ProductServiceDependency,
) -> ProductResponse:
    return _response(
        await service.update_owned(
            product_id,
            identity.user.id,
            ProductUpdate(
                payload.model_dump(exclude={"version"}, exclude_unset=True),
                payload.version,
                identity.user.id,
            ),
        )
    )


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def delete_product(
    product_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: ProductServiceDependency,
) -> Response:
    await service.delete_owned(product_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
