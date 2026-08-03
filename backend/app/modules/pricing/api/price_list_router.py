from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.pricing.api.dependencies import (
    PriceListServiceDependency,
    PricingResolverDependency,
)
from app.modules.pricing.api.price_list_schemas import (
    AssignPriceRequest as AssignPriceApiRequest,
)
from app.modules.pricing.api.price_list_schemas import (
    PriceAssignmentResponse,
    PriceListCreateRequest,
    PriceListPageResponse,
    PriceListResponse,
    PriceListUpdateRequest,
    ResolvedPriceResponse,
)
from app.modules.pricing.application.price_list_schemas import (
    AssignPriceRequest,
    PriceListCreate,
    PriceListFilter,
    PriceListUpdate,
    ResolvePriceRequest,
)
from app.modules.pricing.domain import CustomerGroup, PriceListStatus

price_list_router = APIRouter(prefix="/price-lists", tags=["Price Lists"])
resolver_router = APIRouter(prefix="/pricing", tags=["Pricing Resolution"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Pricing permission"},
    404: {"description": "Resource not found or belongs to another Store"},
}


def _price_list_response(value: Any) -> PriceListResponse:
    return PriceListResponse.model_validate(value, from_attributes=True)


@price_list_router.post(
    "",
    response_model=PriceListResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("price:list:create")],
    responses={**_RESPONSES, 409: {"description": "Price List conflict"}},
)
async def create_price_list(
    payload: PriceListCreateRequest,
    identity: CurrentIdentity,
    service: PriceListServiceDependency,
    response: Response,
) -> PriceListResponse:
    price_list = await service.create(
        PriceListCreate(
            store_id=payload.store_id,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            currency_code=payload.currency_code,
            priority=payload.priority,
            status=payload.status,
            customer_group=payload.customer_group,
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
            is_default=payload.is_default,
            actor_id=identity.user.id,
        )
    )
    response.headers["Location"] = f"/api/v1/price-lists/{price_list.id}"
    return _price_list_response(price_list)


@price_list_router.get(
    "",
    response_model=PriceListPageResponse,
    dependencies=[require_permission("price:list:view")],
    responses=_RESPONSES,
)
async def list_price_lists(
    identity: CurrentIdentity,
    service: PriceListServiceDependency,
    store_id: UUID | None = None,
    currency: str | None = None,
    status_filter: Annotated[PriceListStatus | None, Query(alias="status")] = None,
    customer_group: CustomerGroup | None = None,
    effective_at: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PriceListPageResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    items, total = await service.list_owned(
        identity.user.id,
        PriceListFilter(
            store_id=store_id,
            currency=currency,
            status=status_filter,
            customer_group=customer_group,
            effective_at=effective_at,
            offset=offset,
            limit=limit,
        ),
    )
    return PriceListPageResponse(
        items=[_price_list_response(item) for item in items],
        page=PageMetadata(
            has_more=offset + len(items) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@price_list_router.get(
    "/{price_list_id}",
    response_model=PriceListResponse,
    dependencies=[require_permission("price:list:view")],
    responses=_RESPONSES,
)
async def get_price_list(
    price_list_id: UUID,
    identity: CurrentIdentity,
    service: PriceListServiceDependency,
) -> PriceListResponse:
    return _price_list_response(
        await service.get_owned(price_list_id, identity.user.id)
    )


@price_list_router.patch(
    "/{price_list_id}",
    response_model=PriceListResponse,
    dependencies=[require_permission("price:list:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def update_price_list(
    price_list_id: UUID,
    payload: PriceListUpdateRequest,
    identity: CurrentIdentity,
    service: PriceListServiceDependency,
) -> PriceListResponse:
    return _price_list_response(
        await service.update_owned(
            price_list_id,
            identity.user.id,
            PriceListUpdate(
                values=payload.model_dump(exclude={"version"}, exclude_unset=True),
                expected_version=payload.version,
                actor_id=identity.user.id,
            ),
        )
    )


@price_list_router.delete(
    "/{price_list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("price:list:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def delete_price_list(
    price_list_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: PriceListServiceDependency,
) -> Response:
    await service.delete_owned(price_list_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@price_list_router.post(
    "/{price_list_id}/prices",
    response_model=PriceAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("price:list:update")],
    responses={**_RESPONSES, 409: {"description": "Assignment conflict"}},
)
async def assign_price(
    price_list_id: UUID,
    payload: AssignPriceApiRequest,
    identity: CurrentIdentity,
    service: PriceListServiceDependency,
) -> PriceAssignmentResponse:
    assignment = await service.assign(
        price_list_id,
        identity.user.id,
        AssignPriceRequest(price_id=payload.price_id, actor_id=identity.user.id),
    )
    return PriceAssignmentResponse.model_validate(assignment, from_attributes=True)


@price_list_router.delete(
    "/{price_list_id}/prices/{price_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("price:list:update")],
    responses=_RESPONSES,
)
async def unassign_price(
    price_list_id: UUID,
    price_id: UUID,
    identity: CurrentIdentity,
    service: PriceListServiceDependency,
) -> Response:
    await service.unassign(price_list_id, price_id, identity.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@resolver_router.get(
    "/resolve",
    response_model=ResolvedPriceResponse,
    dependencies=[require_permission("price:resolve")],
    responses=_RESPONSES,
)
async def resolve_price(
    store_id: UUID,
    product_id: UUID,
    identity: CurrentIdentity,
    service: PricingResolverDependency,
    variant_id: UUID | None = None,
    currency: str = "USD",
    customer_group: CustomerGroup = CustomerGroup.PUBLIC,
    timestamp: datetime | None = None,
) -> ResolvedPriceResponse:
    resolved = await service.resolve(
        ResolvePriceRequest(
            store_id=store_id,
            product_id=product_id,
            variant_id=variant_id,
            currency=currency,
            customer_group=customer_group,
            timestamp=timestamp or datetime.now(UTC),
            actor_id=identity.user.id,
        )
    )
    return ResolvedPriceResponse.model_validate(resolved, from_attributes=True)
