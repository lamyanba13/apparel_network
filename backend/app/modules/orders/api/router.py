from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.orders.api.dependencies import OrderServiceDependency
from app.modules.orders.api.schemas import (
    OrderConfirmRequest,
    OrderCreateRequest,
    OrderItemResponse,
    OrderListResponse,
    OrderResponse,
    OrderSummaryResponse,
)
from app.modules.orders.application.schemas import (
    OrderConfirm,
    OrderCreate,
    OrderFilter,
)
from app.modules.orders.domain import OrderStatus

router = APIRouter(prefix="/orders", tags=["Orders"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Order permission"},
    404: {"description": "Order resource not found or owned by another customer"},
}


def _order(value: Any) -> OrderResponse:
    return OrderResponse.model_validate(value, from_attributes=True)


def _item(value: Any) -> OrderItemResponse:
    return OrderItemResponse.model_validate(value, from_attributes=True)


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("order:create")],
    responses={**_RESPONSES, 409: {"description": "Order creation conflict"}},
)
async def create_order(
    payload: OrderCreateRequest,
    identity: CurrentIdentity,
    service: OrderServiceDependency,
    response: Response,
) -> OrderResponse:
    order = await service.create(
        OrderCreate(
            checkout_session_id=payload.checkout_session_id,
            actor_id=identity.user.id,
        )
    )
    response.headers["Location"] = f"/api/v1/orders/{order.id}"
    return _order(order)


@router.get(
    "",
    response_model=OrderListResponse,
    dependencies=[require_permission("order:view")],
    responses=_RESPONSES,
)
async def list_orders(
    identity: CurrentIdentity,
    service: OrderServiceDependency,
    store_id: UUID | None = None,
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> OrderListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    orders, total = await service.list_owned(
        identity.user.id,
        OrderFilter(
            store_id=store_id,
            status=status_filter,
            offset=offset,
            limit=limit,
        ),
    )
    return OrderListResponse(
        items=[_order(value) for value in orders],
        page=PageMetadata(
            has_more=offset + len(orders) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    dependencies=[require_permission("order:view")],
    responses=_RESPONSES,
)
async def get_order(
    order_id: UUID,
    identity: CurrentIdentity,
    service: OrderServiceDependency,
) -> OrderResponse:
    return _order(await service.get_owned(order_id, identity.user.id))


@router.post(
    "/{order_id}/confirm",
    response_model=OrderResponse,
    dependencies=[require_permission("order:confirm")],
    responses={**_RESPONSES, 409: {"description": "Order version conflict"}},
)
async def confirm_order(
    order_id: UUID,
    payload: OrderConfirmRequest,
    identity: CurrentIdentity,
    service: OrderServiceDependency,
) -> OrderResponse:
    return _order(
        await service.confirm_owned(
            order_id,
            identity.user.id,
            OrderConfirm(
                expected_version=payload.version,
                actor_id=identity.user.id,
            ),
        )
    )


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("order:update")],
    responses={**_RESPONSES, 409: {"description": "Order version conflict"}},
)
async def cancel_order(
    order_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: OrderServiceDependency,
) -> Response:
    await service.cancel_owned(order_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{order_id}/summary",
    response_model=OrderSummaryResponse,
    dependencies=[require_permission("order:view")],
    responses=_RESPONSES,
)
async def order_summary(
    order_id: UUID,
    identity: CurrentIdentity,
    service: OrderServiceDependency,
) -> OrderSummaryResponse:
    summary = await service.summary_owned(order_id, identity.user.id)
    return OrderSummaryResponse(
        order_id=summary.order_id,
        items=[_item(item) for item in summary.items],
        subtotal=summary.subtotal,
        currency=summary.currency,
        quantity=summary.quantity,
    )
