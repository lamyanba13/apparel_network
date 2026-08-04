from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.cart.api.dependencies import CartServiceDependency
from app.modules.cart.api.schemas import (
    CartCreateRequest,
    CartItemCreateRequest,
    CartItemResponse,
    CartItemUpdateRequest,
    CartListResponse,
    CartResponse,
    CartSummaryResponse,
)
from app.modules.cart.application.schemas import (
    CartCreate,
    CartFilter,
    CartItemCreate,
    CartItemUpdate,
)
from app.modules.cart.domain import CartStatus
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity

router = APIRouter(prefix="/cart", tags=["Shopping Cart"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Cart permission"},
    404: {"description": "Cart resource not found or owned by another user"},
}


def _cart(value: Any) -> CartResponse:
    return CartResponse.model_validate(value, from_attributes=True)


def _item(value: Any) -> CartItemResponse:
    return CartItemResponse.model_validate(value, from_attributes=True)


@router.post(
    "",
    response_model=CartResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("cart:create")],
    responses={**_RESPONSES, 409: {"description": "Active Cart conflict"}},
)
async def create_cart(
    payload: CartCreateRequest,
    identity: CurrentIdentity,
    service: CartServiceDependency,
    response: Response,
) -> CartResponse:
    cart = await service.create(
        CartCreate(
            store_id=payload.store_id,
            currency=payload.currency,
            customer_group=payload.customer_group,
            expires_at=payload.expires_at,
            actor_id=identity.user.id,
        )
    )
    response.headers["Location"] = f"/api/v1/cart/{cart.id}"
    return _cart(cart)


@router.get(
    "",
    response_model=CartListResponse,
    dependencies=[require_permission("cart:view")],
    responses=_RESPONSES,
)
async def list_carts(
    identity: CurrentIdentity,
    service: CartServiceDependency,
    store_id: UUID | None = None,
    status_filter: Annotated[CartStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CartListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    carts, total = await service.list_owned(
        identity.user.id,
        CartFilter(
            store_id=store_id,
            status=status_filter,
            offset=offset,
            limit=limit,
        ),
    )
    return CartListResponse(
        items=[_cart(cart) for cart in carts],
        page=PageMetadata(
            has_more=offset + len(carts) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/{cart_id}",
    response_model=CartResponse,
    dependencies=[require_permission("cart:view")],
    responses=_RESPONSES,
)
async def get_cart(
    cart_id: UUID,
    identity: CurrentIdentity,
    service: CartServiceDependency,
) -> CartResponse:
    return _cart(await service.get_owned(cart_id, identity.user.id))


@router.post(
    "/{cart_id}/items",
    response_model=CartItemResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("cart:update")],
    responses={**_RESPONSES, 409: {"description": "Cart Item conflict"}},
)
async def add_cart_item(
    cart_id: UUID,
    payload: CartItemCreateRequest,
    identity: CurrentIdentity,
    service: CartServiceDependency,
) -> CartItemResponse:
    return _item(
        await service.add_item(
            cart_id,
            identity.user.id,
            CartItemCreate(
                variant_id=payload.variant_id,
                quantity=payload.quantity,
                expected_cart_version=payload.version,
                actor_id=identity.user.id,
            ),
        )
    )


@router.patch(
    "/{cart_id}/items/{item_id}",
    response_model=CartItemResponse,
    dependencies=[require_permission("cart:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def update_cart_item(
    cart_id: UUID,
    item_id: UUID,
    payload: CartItemUpdateRequest,
    identity: CurrentIdentity,
    service: CartServiceDependency,
) -> CartItemResponse:
    return _item(
        await service.update_item(
            cart_id,
            item_id,
            identity.user.id,
            CartItemUpdate(
                quantity=payload.quantity,
                expected_version=payload.version,
                actor_id=identity.user.id,
            ),
        )
    )


@router.delete(
    "/{cart_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("cart:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def remove_cart_item(
    cart_id: UUID,
    item_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: CartServiceDependency,
) -> Response:
    await service.remove_item(
        cart_id,
        item_id,
        identity.user.id,
        expected_version=version,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{cart_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("cart:delete")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def delete_cart(
    cart_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: CartServiceDependency,
) -> Response:
    await service.delete_owned(cart_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{cart_id}/summary",
    response_model=CartSummaryResponse,
    dependencies=[require_permission("cart:view")],
    responses=_RESPONSES,
)
async def cart_summary(
    cart_id: UUID,
    identity: CurrentIdentity,
    service: CartServiceDependency,
) -> CartSummaryResponse:
    summary = await service.summary_owned(cart_id, identity.user.id)
    return CartSummaryResponse(
        cart_id=summary.cart_id,
        items=[_item(item) for item in summary.items],
        subtotal=summary.subtotal,
        currency=summary.currency,
        quantity=summary.quantity,
    )
