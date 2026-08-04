from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.checkout.api.dependencies import CheckoutServiceDependency
from app.modules.checkout.api.schemas import (
    CheckoutConfirmRequest,
    CheckoutCreateRequest,
    CheckoutItemResponse,
    CheckoutListResponse,
    CheckoutResponse,
    CheckoutSummaryResponse,
)
from app.modules.checkout.application.schemas import (
    CheckoutConfirm,
    CheckoutCreate,
    CheckoutFilter,
)
from app.modules.checkout.domain import CheckoutStatus
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity

router = APIRouter(prefix="/checkout", tags=["Checkout"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Checkout permission"},
    404: {"description": "Checkout resource not found or owned by another user"},
}


def _checkout(value: Any) -> CheckoutResponse:
    return CheckoutResponse.model_validate(value, from_attributes=True)


def _item(value: Any) -> CheckoutItemResponse:
    return CheckoutItemResponse.model_validate(value, from_attributes=True)


@router.post(
    "",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("checkout:create")],
    responses={**_RESPONSES, 409: {"description": "Checkout validation conflict"}},
)
async def create_checkout(
    payload: CheckoutCreateRequest,
    identity: CurrentIdentity,
    service: CheckoutServiceDependency,
    response: Response,
) -> CheckoutResponse:
    checkout = await service.create(
        CheckoutCreate(
            cart_id=payload.cart_id,
            expires_at=payload.expires_at,
            actor_id=identity.user.id,
        )
    )
    response.headers["Location"] = f"/api/v1/checkout/{checkout.id}"
    return _checkout(checkout)


@router.get(
    "",
    response_model=CheckoutListResponse,
    dependencies=[require_permission("checkout:view")],
    responses=_RESPONSES,
)
async def list_checkouts(
    identity: CurrentIdentity,
    service: CheckoutServiceDependency,
    status_filter: Annotated[CheckoutStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CheckoutListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    checkouts, total = await service.list_owned(
        identity.user.id,
        CheckoutFilter(status=status_filter, offset=offset, limit=limit),
    )
    return CheckoutListResponse(
        items=[_checkout(value) for value in checkouts],
        page=PageMetadata(
            has_more=offset + len(checkouts) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/{checkout_id}",
    response_model=CheckoutResponse,
    dependencies=[require_permission("checkout:view")],
    responses=_RESPONSES,
)
async def get_checkout(
    checkout_id: UUID,
    identity: CurrentIdentity,
    service: CheckoutServiceDependency,
) -> CheckoutResponse:
    return _checkout(await service.get_owned(checkout_id, identity.user.id))


@router.post(
    "/{checkout_id}/confirm",
    response_model=CheckoutResponse,
    dependencies=[require_permission("checkout:confirm")],
    responses={**_RESPONSES, 409: {"description": "Checkout version conflict"}},
)
async def confirm_checkout(
    checkout_id: UUID,
    payload: CheckoutConfirmRequest,
    identity: CurrentIdentity,
    service: CheckoutServiceDependency,
) -> CheckoutResponse:
    return _checkout(
        await service.confirm_owned(
            checkout_id,
            identity.user.id,
            CheckoutConfirm(
                expected_version=payload.version,
                actor_id=identity.user.id,
            ),
        )
    )


@router.delete(
    "/{checkout_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("checkout:update")],
    responses={**_RESPONSES, 409: {"description": "Checkout version conflict"}},
)
async def cancel_checkout(
    checkout_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: CheckoutServiceDependency,
) -> Response:
    await service.cancel_owned(checkout_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{checkout_id}/summary",
    response_model=CheckoutSummaryResponse,
    dependencies=[require_permission("checkout:view")],
    responses=_RESPONSES,
)
async def checkout_summary(
    checkout_id: UUID,
    identity: CurrentIdentity,
    service: CheckoutServiceDependency,
) -> CheckoutSummaryResponse:
    summary = await service.summary_owned(checkout_id, identity.user.id)
    return CheckoutSummaryResponse(
        checkout_session_id=summary.checkout_session_id,
        items=[_item(item) for item in summary.items],
        subtotal=summary.subtotal,
        currency=summary.currency,
        quantity=summary.quantity,
    )
