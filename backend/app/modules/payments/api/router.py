from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.common.api.dependencies import idempotency_key_dependency
from app.common.idempotency import IdempotencyKey
from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.payments.api.dependencies import PaymentServiceDependency
from app.modules.payments.api.schemas import (
    PaymentCreateRequest,
    PaymentDetailResponse,
    PaymentIntentResponse,
    PaymentListResponse,
    PaymentStatusResponse,
    PaymentTransactionResponse,
    PaymentTransitionRequest,
)
from app.modules.payments.application.schemas import (
    PaymentCreate,
    PaymentFilter,
    PaymentTransition,
)
from app.modules.payments.domain import PaymentStatus

router: APIRouter = APIRouter(prefix="/payments", tags=["Payments"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Payment permission"},
    404: {"description": "Payment resource not found or owned by another customer"},
}


def _payment(value: Any) -> PaymentIntentResponse:
    return PaymentIntentResponse.model_validate(value, from_attributes=True)


@router.post(
    "",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("payment:create")],
    responses={**_RESPONSES, 409: {"description": "Payment creation conflict"}},
)
async def create_payment(
    payload: PaymentCreateRequest,
    identity: CurrentIdentity,
    service: PaymentServiceDependency,
    response: Response,
    idempotency_key: Annotated[IdempotencyKey, Depends(idempotency_key_dependency)],
) -> PaymentIntentResponse:
    payment = await service.create(
        PaymentCreate(
            order_id=payload.order_id,
            customer_id=identity.user.id,
            idempotency_key=idempotency_key.value,
        )
    )
    response.headers["Location"] = f"/api/v1/payments/{payment.id}"
    return _payment(payment)


@router.get(
    "",
    response_model=PaymentListResponse,
    dependencies=[require_permission("payment:view")],
    responses=_RESPONSES,
)
async def list_payments(
    identity: CurrentIdentity,
    service: PaymentServiceDependency,
    store_id: UUID | None = None,
    order_id: UUID | None = None,
    status_filter: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PaymentListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    payments, total = await service.list_owned(
        identity.user.id,
        PaymentFilter(
            store_id=store_id,
            order_id=order_id,
            status=status_filter,
            offset=offset,
            limit=limit,
        ),
    )
    return PaymentListResponse(
        items=[_payment(value) for value in payments],
        page=PageMetadata(
            has_more=offset + len(payments) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentDetailResponse,
    dependencies=[require_permission("payment:view")],
    responses=_RESPONSES,
)
async def get_payment(
    payment_id: UUID,
    identity: CurrentIdentity,
    service: PaymentServiceDependency,
) -> PaymentDetailResponse:
    payment = await service.get_owned(payment_id, identity.user.id)
    transactions = await service.transactions_owned(payment.id, identity.user.id)
    return PaymentDetailResponse(
        **_payment(payment).model_dump(),
        transactions=[
            PaymentTransactionResponse.model_validate(value, from_attributes=True)
            for value in transactions
        ],
    )


@router.post(
    "/{payment_id}/authorize",
    response_model=PaymentIntentResponse,
    dependencies=[require_permission("payment:update")],
    responses={**_RESPONSES, 409: {"description": "Payment transition conflict"}},
)
async def authorize_payment(
    payment_id: UUID,
    payload: PaymentTransitionRequest,
    identity: CurrentIdentity,
    service: PaymentServiceDependency,
) -> PaymentIntentResponse:
    return _payment(
        await service.authorize_owned(
            payment_id,
            identity.user.id,
            PaymentTransition(payload.version, identity.user.id),
        )
    )


@router.post(
    "/{payment_id}/capture",
    response_model=PaymentIntentResponse,
    dependencies=[require_permission("payment:capture")],
    responses={**_RESPONSES, 409: {"description": "Payment transition conflict"}},
)
async def capture_payment(
    payment_id: UUID,
    payload: PaymentTransitionRequest,
    identity: CurrentIdentity,
    service: PaymentServiceDependency,
) -> PaymentIntentResponse:
    return _payment(
        await service.capture_owned(
            payment_id,
            identity.user.id,
            PaymentTransition(payload.version, identity.user.id),
        )
    )


@router.post(
    "/{payment_id}/cancel",
    response_model=PaymentIntentResponse,
    dependencies=[require_permission("payment:cancel")],
    responses={**_RESPONSES, 409: {"description": "Payment transition conflict"}},
)
async def cancel_payment(
    payment_id: UUID,
    payload: PaymentTransitionRequest,
    identity: CurrentIdentity,
    service: PaymentServiceDependency,
) -> PaymentIntentResponse:
    return _payment(
        await service.cancel_owned(
            payment_id,
            identity.user.id,
            PaymentTransition(payload.version, identity.user.id),
        )
    )


@router.get(
    "/{payment_id}/status",
    response_model=PaymentStatusResponse,
    dependencies=[require_permission("payment:view")],
    responses=_RESPONSES,
)
async def payment_status(
    payment_id: UUID,
    identity: CurrentIdentity,
    service: PaymentServiceDependency,
) -> PaymentStatusResponse:
    payment = await service.get_owned(payment_id, identity.user.id)
    gateway_status = await service.status_owned(payment.id, identity.user.id)
    return PaymentStatusResponse(
        payment_id=payment.id,
        provider=payment.provider,
        provider_reference=gateway_status.provider_reference,
        status=gateway_status.status,
        checked_at=datetime.now(UTC),
    )
