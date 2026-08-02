from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.products.api.dependencies import ProductVariantServiceDependency
from app.modules.products.api.schemas import (
    ProductVariantCreateRequest,
    ProductVariantResponse,
    ProductVariantUpdateRequest,
)
from app.modules.products.application.variant_schemas import (
    ProductVariantCreate,
    ProductVariantUpdate,
)

router = APIRouter(prefix="/products/{product_id}/variants", tags=["Product Variants"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Catalog permission"},
    404: {"description": "Product or variant not found or not owned by this identity"},
}


def _response(variant: Any) -> ProductVariantResponse:
    return ProductVariantResponse.model_validate(variant, from_attributes=True)


@router.post(
    "",
    response_model=ProductVariantResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Reference or attribute conflict"}},
)
async def create_variant(
    product_id: UUID,
    payload: ProductVariantCreateRequest,
    identity: CurrentIdentity,
    service: ProductVariantServiceDependency,
    response: Response,
) -> ProductVariantResponse:
    variant = await service.create(
        product_id,
        ProductVariantCreate(
            payload.reference, payload.attributes, payload.sort_order, identity.user.id
        ),
    )
    response.headers["Location"] = (
        f"/api/v1/products/{product_id}/variants/{variant.id}"
    )
    return _response(variant)


@router.get(
    "",
    response_model=list[ProductVariantResponse],
    dependencies=[require_permission("catalog:view")],
    responses=_RESPONSES,
)
async def list_variants(
    product_id: UUID,
    identity: CurrentIdentity,
    service: ProductVariantServiceDependency,
) -> list[ProductVariantResponse]:
    return [
        _response(variant)
        for variant in await service.list_owned(product_id, identity.user.id)
    ]


@router.patch(
    "/{variant_id}",
    response_model=ProductVariantResponse,
    dependencies=[require_permission("catalog:update")],
    responses={
        **_RESPONSES,
        409: {"description": "Optimistic, reference, or attribute conflict"},
    },
)
async def update_variant(
    product_id: UUID,
    variant_id: UUID,
    payload: ProductVariantUpdateRequest,
    identity: CurrentIdentity,
    service: ProductVariantServiceDependency,
) -> ProductVariantResponse:
    variant = await service.update_owned(
        variant_id,
        product_id,
        identity.user.id,
        ProductVariantUpdate(
            payload.model_dump(exclude={"version"}, exclude_unset=True),
            payload.version,
            identity.user.id,
        ),
    )
    return _response(variant)


@router.delete(
    "/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("catalog:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def delete_variant(
    product_id: UUID,
    variant_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: ProductVariantServiceDependency,
) -> Response:
    await service.delete_owned(variant_id, product_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
