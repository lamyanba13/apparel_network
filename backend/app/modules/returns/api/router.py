from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.returns.api.dependencies import (
    RefundServiceDependency,
    ReturnServiceDependency,
)
from app.modules.returns.api.schemas import (
    LifecycleRequest,
    RefundCreateRequest,
    RefundDetailResponse,
    RefundListResponse,
    RefundResponse,
    RefundStatusResponse,
    RefundTransactionResponse,
    ReturnCreateRequest,
    ReturnDetailResponse,
    ReturnInspectionRequest,
    ReturnItemResponse,
    ReturnListResponse,
    ReturnResponse,
    ReturnSummaryResponse,
    ReturnUpdateRequest,
)
from app.modules.returns.application.schemas import (
    RefundCreate,
    RefundFilter,
    RefundTransition,
    ReturnCreate,
    ReturnFilter,
    ReturnInspection,
    ReturnItemCreate,
    ReturnTransition,
    ReturnUpdate,
)
from app.modules.returns.domain import InventoryDisposition, RefundStatus, ReturnStatus

router = APIRouter(tags=["Returns and Refunds"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required permission"},
    404: {"description": "Resource not found or owned by another customer"},
}


def _return(value: Any) -> ReturnResponse:
    return ReturnResponse.model_validate(value, from_attributes=True)


def _refund(value: Any) -> RefundResponse:
    return RefundResponse.model_validate(value, from_attributes=True)


@router.post(
    "/returns",
    response_model=ReturnResponse,
    status_code=201,
    dependencies=[require_permission("return:create")],
    responses={**_RESPONSES, 409: {"description": "Return conflict"}},
)
async def create_return(
    payload: ReturnCreateRequest,
    identity: CurrentIdentity,
    service: ReturnServiceDependency,
) -> ReturnResponse:
    return _return(
        await service.create(
            ReturnCreate(
                payload.order_id,
                payload.shipment_id,
                payload.payment_id,
                payload.reason,
                tuple(
                    ReturnItemCreate(item.order_item_id, item.quantity)
                    for item in payload.items
                ),
                identity.user.id,
            )
        )
    )


@router.get(
    "/returns",
    response_model=ReturnListResponse,
    dependencies=[require_permission("return:view")],
    responses=_RESPONSES,
)
async def list_returns(
    identity: CurrentIdentity,
    service: ReturnServiceDependency,
    store_id: UUID | None = None,
    order_id: UUID | None = None,
    status_filter: Annotated[ReturnStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ReturnListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    values, total = await service.list_owned(
        identity.user.id,
        ReturnFilter(store_id, order_id, status_filter, offset, limit),
    )
    return ReturnListResponse(
        items=[_return(value) for value in values],
        page=PageMetadata(
            has_more=offset + len(values) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/returns/{return_id}",
    response_model=ReturnDetailResponse,
    dependencies=[require_permission("return:view")],
    responses=_RESPONSES,
)
async def get_return(
    return_id: UUID,
    identity: CurrentIdentity,
    service: ReturnServiceDependency,
) -> ReturnDetailResponse:
    result, items = await service.detail_owned(return_id, identity.user.id)
    return ReturnDetailResponse(
        **_return(result).model_dump(),
        items=[ReturnItemResponse.model_validate(item) for item in items],
    )


@router.patch(
    "/returns/{return_id}",
    response_model=ReturnResponse,
    dependencies=[require_permission("return:update")],
    responses={**_RESPONSES, 409: {"description": "Return conflict"}},
)
async def update_return(
    return_id: UUID,
    payload: ReturnUpdateRequest,
    identity: CurrentIdentity,
    service: ReturnServiceDependency,
) -> ReturnResponse:
    return _return(
        await service.update_owned(
            return_id,
            identity.user.id,
            ReturnUpdate(payload.reason, payload.version, identity.user.id),
        )
    )


async def _return_transition(
    operation: str,
    return_id: UUID,
    payload: LifecycleRequest,
    identity: CurrentIdentity,
    service: ReturnServiceDependency,
) -> ReturnResponse:
    values = ReturnTransition(payload.version, identity.user.id)
    methods = {
        "approve": service.approve_owned,
        "receive": service.receive_owned,
        "reject": service.reject_owned,
        "cancel": service.cancel_owned,
    }
    return _return(await methods[operation](return_id, identity.user.id, values))


@router.post(
    "/returns/{return_id}/approve",
    response_model=ReturnResponse,
    dependencies=[require_permission("return:approve")],
    responses={**_RESPONSES, 409: {"description": "Return conflict"}},
)
async def approve_return(
    return_id: UUID,
    payload: LifecycleRequest,
    identity: CurrentIdentity,
    service: ReturnServiceDependency,
) -> ReturnResponse:
    return await _return_transition("approve", return_id, payload, identity, service)


@router.post(
    "/returns/{return_id}/receive",
    response_model=ReturnResponse,
    dependencies=[require_permission("return:receive")],
    responses={**_RESPONSES, 409: {"description": "Return conflict"}},
)
async def receive_return(
    return_id: UUID,
    payload: LifecycleRequest,
    identity: CurrentIdentity,
    service: ReturnServiceDependency,
) -> ReturnResponse:
    return await _return_transition("receive", return_id, payload, identity, service)


@router.post(
    "/returns/{return_id}/inspect",
    response_model=ReturnResponse,
    dependencies=[require_permission("return:inspect")],
    responses={**_RESPONSES, 409: {"description": "Return conflict"}},
)
async def inspect_return(
    return_id: UUID,
    payload: ReturnInspectionRequest,
    identity: CurrentIdentity,
    service: ReturnServiceDependency,
) -> ReturnResponse:
    dispositions = {
        item.return_item_id: item.disposition for item in payload.dispositions
    }
    return _return(
        await service.inspect_owned(
            return_id,
            identity.user.id,
            ReturnInspection(payload.version, dispositions, identity.user.id),
        )
    )


@router.post(
    "/returns/{return_id}/reject",
    response_model=ReturnResponse,
    dependencies=[require_permission("return:reject")],
    responses={**_RESPONSES, 409: {"description": "Return conflict"}},
)
async def reject_return(
    return_id: UUID,
    payload: LifecycleRequest,
    identity: CurrentIdentity,
    service: ReturnServiceDependency,
) -> ReturnResponse:
    return await _return_transition("reject", return_id, payload, identity, service)


@router.post(
    "/returns/{return_id}/cancel",
    response_model=ReturnResponse,
    dependencies=[require_permission("return:update")],
    responses={**_RESPONSES, 409: {"description": "Return conflict"}},
)
async def cancel_return(
    return_id: UUID,
    payload: LifecycleRequest,
    identity: CurrentIdentity,
    service: ReturnServiceDependency,
) -> ReturnResponse:
    return await _return_transition("cancel", return_id, payload, identity, service)


@router.get(
    "/returns/{return_id}/summary",
    response_model=ReturnSummaryResponse,
    dependencies=[require_permission("return:view")],
    responses=_RESPONSES,
)
async def return_summary(
    return_id: UUID,
    identity: CurrentIdentity,
    service: ReturnServiceDependency,
) -> ReturnSummaryResponse:
    result, items = await service.detail_owned(return_id, identity.user.id)
    dispositions = {disposition: 0 for disposition in InventoryDisposition}
    for item in items:
        dispositions[item.disposition] += item.quantity
    return ReturnSummaryResponse(
        return_id=result.id,
        status=result.status,
        item_quantity=sum(item.quantity for item in items),
        refundable_amount=sum(
            (item.unit_price * item.quantity for item in items), start=Decimal()
        ),
        currency=items[0].currency,
        dispositions=dispositions,
    )


@router.post(
    "/refunds",
    response_model=RefundResponse,
    status_code=201,
    dependencies=[require_permission("refund:create")],
    responses={**_RESPONSES, 409: {"description": "Refund conflict"}},
)
async def create_refund(
    payload: RefundCreateRequest,
    identity: CurrentIdentity,
    service: RefundServiceDependency,
) -> RefundResponse:
    return _refund(
        await service.create(RefundCreate(payload.return_id, identity.user.id))
    )


@router.get(
    "/refunds",
    response_model=RefundListResponse,
    dependencies=[require_permission("refund:view")],
    responses=_RESPONSES,
)
async def list_refunds(
    identity: CurrentIdentity,
    service: RefundServiceDependency,
    return_id: UUID | None = None,
    status_filter: Annotated[RefundStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> RefundListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    values, total = await service.list_owned(
        identity.user.id, RefundFilter(return_id, status_filter, offset, limit)
    )
    return RefundListResponse(
        items=[_refund(value) for value in values],
        page=PageMetadata(
            has_more=offset + len(values) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/refunds/{refund_id}",
    response_model=RefundDetailResponse,
    dependencies=[require_permission("refund:view")],
    responses=_RESPONSES,
)
async def get_refund(
    refund_id: UUID,
    identity: CurrentIdentity,
    service: RefundServiceDependency,
) -> RefundDetailResponse:
    refund, transactions = await service.detail_owned(refund_id, identity.user.id)
    return RefundDetailResponse(
        **_refund(refund).model_dump(),
        transactions=[
            RefundTransactionResponse.model_validate(value) for value in transactions
        ],
    )


@router.post(
    "/refunds/{refund_id}/process",
    response_model=RefundResponse,
    dependencies=[require_permission("refund:process")],
    responses={**_RESPONSES, 409: {"description": "Refund conflict"}},
)
async def process_refund(
    refund_id: UUID,
    payload: LifecycleRequest,
    identity: CurrentIdentity,
    service: RefundServiceDependency,
) -> RefundResponse:
    return _refund(
        await service.process_owned(
            refund_id,
            identity.user.id,
            RefundTransition(payload.version, identity.user.id),
        )
    )


@router.get(
    "/refunds/{refund_id}/status",
    response_model=RefundStatusResponse,
    dependencies=[require_permission("refund:view")],
    responses=_RESPONSES,
)
async def refund_status(
    refund_id: UUID,
    identity: CurrentIdentity,
    service: RefundServiceDependency,
) -> RefundStatusResponse:
    refund = await service.get_owned(refund_id, identity.user.id)
    return RefundStatusResponse(
        refund_id=refund.id, status=refund.status, checked_at=datetime.now(UTC)
    )
