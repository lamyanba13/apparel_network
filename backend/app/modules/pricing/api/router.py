from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.pricing.api.dependencies import PricingServiceDependency
from app.modules.pricing.api.schemas import (
    ProductPriceCreateRequest,
    ProductPriceListResponse,
    ProductPriceResponse,
    ProductPriceUpdateRequest,
)
from app.modules.pricing.application.schemas import (
    ProductPriceCreate,
    ProductPriceFilter,
    ProductPriceUpdate,
)
from app.modules.pricing.domain import PriceStatus

router = APIRouter(prefix="/prices", tags=["Product Pricing"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Pricing permission"},
    404: {"description": "Product Price not found or not owned by this identity"},
}


def _response(price: Any) -> ProductPriceResponse:
    return ProductPriceResponse.model_validate(price, from_attributes=True)


@router.post(
    "",
    response_model=ProductPriceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("price:create")],
    responses={**_RESPONSES, 409: {"description": "Active price conflict"}},
)
async def create_price(
    payload: ProductPriceCreateRequest,
    identity: CurrentIdentity,
    service: PricingServiceDependency,
    response: Response,
) -> ProductPriceResponse:
    price = await service.create(
        ProductPriceCreate(
            store_id=payload.store_id,
            product_id=payload.product_id,
            variant_id=payload.variant_id,
            currency_code=payload.currency_code,
            base_price=payload.base_price,
            sale_price=payload.sale_price,
            compare_at_price=payload.compare_at_price,
            cost_price=payload.cost_price,
            tax_class=payload.tax_class,
            status=payload.status,
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
            actor_id=identity.user.id,
        )
    )
    response.headers["Location"] = f"/api/v1/prices/{price.id}"
    return _response(price)


@router.get(
    "",
    response_model=ProductPriceListResponse,
    dependencies=[require_permission("price:view")],
    responses=_RESPONSES,
)
async def list_prices(
    identity: CurrentIdentity,
    service: PricingServiceDependency,
    store_id: UUID | None = None,
    product_id: UUID | None = None,
    variant_id: UUID | None = None,
    currency: str | None = None,
    status_filter: Annotated[PriceStatus | None, Query(alias="status")] = None,
    effective_at: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ProductPriceListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    items, total = await service.list_owned(
        identity.user.id,
        ProductPriceFilter(
            store_id=store_id,
            product_id=product_id,
            variant_id=variant_id,
            currency=currency,
            status=status_filter,
            effective_at=effective_at,
            offset=offset,
            limit=limit,
        ),
    )
    return ProductPriceListResponse(
        items=[_response(item) for item in items],
        page=PageMetadata(
            has_more=offset + len(items) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/{price_id}",
    response_model=ProductPriceResponse,
    dependencies=[require_permission("price:view")],
    responses=_RESPONSES,
)
async def get_price(
    price_id: UUID,
    identity: CurrentIdentity,
    service: PricingServiceDependency,
) -> ProductPriceResponse:
    return _response(await service.get_owned(price_id, identity.user.id))


@router.patch(
    "/{price_id}",
    response_model=ProductPriceResponse,
    dependencies=[require_permission("price:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def update_price(
    price_id: UUID,
    payload: ProductPriceUpdateRequest,
    identity: CurrentIdentity,
    service: PricingServiceDependency,
) -> ProductPriceResponse:
    return _response(
        await service.update_owned(
            price_id,
            identity.user.id,
            ProductPriceUpdate(
                values=payload.model_dump(exclude={"version"}, exclude_unset=True),
                expected_version=payload.version,
                actor_id=identity.user.id,
            ),
        )
    )


@router.delete(
    "/{price_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("price:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def delete_price(
    price_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: PricingServiceDependency,
) -> Response:
    await service.delete_owned(price_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
