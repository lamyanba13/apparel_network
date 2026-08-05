from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.promotions.api.dependencies import (
    CouponServiceDependency,
    PromotionEvaluationServiceDependency,
    PromotionServiceDependency,
)
from app.modules.promotions.api.schemas import (
    CouponCreateRequest,
    CouponListResponse,
    CouponResponse,
    CouponUpdateRequest,
    DiscountLineResponse,
    LifecycleRequest,
    PromotionCreateRequest,
    PromotionDetailResponse,
    PromotionEvaluateRequest,
    PromotionEvaluateResponse,
    PromotionListResponse,
    PromotionResponse,
    PromotionRuleResponse,
    PromotionUpdateRequest,
    RejectedPromotionResponse,
)
from app.modules.promotions.application.schemas import (
    CouponCreate,
    CouponFilter,
    CouponUpdate,
    PromotionCreate,
    PromotionEvaluate,
    PromotionFilter,
    PromotionUpdate,
    RuleCreate,
)
from app.modules.promotions.domain import PromotionStatus, PromotionType

router = APIRouter(tags=["Promotions and Discounts"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required permission"},
    404: {"description": "Resource not found or belongs to another Store"},
}


def _promotion(value: Any) -> PromotionResponse:
    return PromotionResponse.model_validate(value, from_attributes=True)


def _coupon(value: Any) -> CouponResponse:
    return CouponResponse.model_validate(value, from_attributes=True)


@router.post(
    "/promotions",
    response_model=PromotionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("promotion:create")],
    responses={**_RESPONSES, 409: {"description": "Promotion conflict"}},
)
async def create_promotion(
    payload: PromotionCreateRequest,
    identity: CurrentIdentity,
    service: PromotionServiceDependency,
) -> PromotionResponse:
    return _promotion(
        await service.create(
            PromotionCreate(
                store_id=payload.store_id,
                name=payload.name,
                description=payload.description,
                promotion_type=payload.promotion_type,
                status=payload.status,
                currency=payload.currency,
                percentage=payload.percentage,
                fixed_amount=payload.fixed_amount,
                buy_quantity=payload.buy_quantity,
                get_quantity=payload.get_quantity,
                bundle_quantity=payload.bundle_quantity,
                bundle_price=payload.bundle_price,
                tiers=tuple(payload.tiers),
                public=payload.public,
                first_purchase_only=payload.first_purchase_only,
                customer_group=payload.customer_group,
                minimum_order_amount=payload.minimum_order_amount,
                minimum_quantity=payload.minimum_quantity,
                maximum_discount=payload.maximum_discount,
                usage_limit=payload.usage_limit,
                per_customer_usage_limit=payload.per_customer_usage_limit,
                exclusive=payload.exclusive,
                stackable=payload.stackable,
                priority=payload.priority,
                maximum_stack=payload.maximum_stack,
                effective_from=payload.effective_from,
                effective_until=payload.effective_until,
                rules=tuple(
                    RuleCreate(rule.condition, rule.configuration)
                    for rule in payload.rules
                ),
                actor_id=identity.user.id,
            )
        )
    )


@router.get(
    "/promotions",
    response_model=PromotionListResponse,
    dependencies=[require_permission("promotion:view")],
    responses=_RESPONSES,
)
async def list_promotions(
    identity: CurrentIdentity,
    service: PromotionServiceDependency,
    store_id: UUID | None = None,
    status_filter: Annotated[PromotionStatus | None, Query(alias="status")] = None,
    promotion_type: PromotionType | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PromotionListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    values, total = await service.list_owned(
        identity.user.id,
        PromotionFilter(store_id, status_filter, promotion_type, offset, limit),
    )
    return PromotionListResponse(
        items=[_promotion(value) for value in values],
        page=PageMetadata(
            has_more=offset + len(values) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.post(
    "/promotions/evaluate",
    response_model=PromotionEvaluateResponse,
    dependencies=[require_permission("coupon:redeem")],
    responses=_RESPONSES,
)
async def evaluate_promotions(
    payload: PromotionEvaluateRequest,
    identity: CurrentIdentity,
    service: PromotionEvaluationServiceDependency,
) -> PromotionEvaluateResponse:
    result = await service.evaluate(
        PromotionEvaluate(
            payload.cart_id, tuple(payload.coupon_codes), identity.user.id
        )
    )
    lines = [
        DiscountLineResponse.model_validate(value)
        for value in result.applied_promotions
    ]
    return PromotionEvaluateResponse(
        cart_id=result.cart_id,
        applied_promotions=lines,
        rejected_promotions=[
            RejectedPromotionResponse.model_validate(value)
            for value in result.rejected_promotions
        ],
        discount_breakdown=lines,
        subtotal=result.subtotal,
        discount_total=result.discount_total,
        final_total=result.final_total,
        currency=result.currency,
        evaluated_at=result.evaluated_at,
    )


@router.get(
    "/promotions/{promotion_id}",
    response_model=PromotionDetailResponse,
    dependencies=[require_permission("promotion:view")],
    responses=_RESPONSES,
)
async def get_promotion(
    promotion_id: UUID,
    identity: CurrentIdentity,
    service: PromotionServiceDependency,
) -> PromotionDetailResponse:
    value, rules = await service.detail_owned(promotion_id, identity.user.id)
    return PromotionDetailResponse(
        **_promotion(value).model_dump(),
        rules=[PromotionRuleResponse.model_validate(rule) for rule in rules],
    )


@router.patch(
    "/promotions/{promotion_id}",
    response_model=PromotionResponse,
    dependencies=[require_permission("promotion:update")],
    responses={**_RESPONSES, 409: {"description": "Promotion version conflict"}},
)
async def update_promotion(
    promotion_id: UUID,
    payload: PromotionUpdateRequest,
    identity: CurrentIdentity,
    service: PromotionServiceDependency,
) -> PromotionResponse:
    values = payload.model_dump(exclude_unset=True, exclude={"version"})
    return _promotion(
        await service.update_owned(
            promotion_id,
            identity.user.id,
            PromotionUpdate(values, payload.version, identity.user.id),
        )
    )


@router.delete(
    "/promotions/{promotion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("promotion:update")],
    responses={**_RESPONSES, 409: {"description": "Promotion version conflict"}},
)
async def delete_promotion(
    promotion_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: PromotionServiceDependency,
) -> Response:
    await service.delete_owned(promotion_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/promotions/{promotion_id}/activate",
    response_model=PromotionResponse,
    dependencies=[require_permission("promotion:activate")],
    responses={**_RESPONSES, 409: {"description": "Promotion lifecycle conflict"}},
)
async def activate_promotion(
    promotion_id: UUID,
    payload: LifecycleRequest,
    identity: CurrentIdentity,
    service: PromotionServiceDependency,
) -> PromotionResponse:
    return _promotion(
        await service.activate_owned(promotion_id, identity.user.id, payload.version)
    )


@router.post(
    "/promotions/{promotion_id}/archive",
    response_model=PromotionResponse,
    dependencies=[require_permission("promotion:archive")],
    responses={**_RESPONSES, 409: {"description": "Promotion lifecycle conflict"}},
)
async def archive_promotion(
    promotion_id: UUID,
    payload: LifecycleRequest,
    identity: CurrentIdentity,
    service: PromotionServiceDependency,
) -> PromotionResponse:
    return _promotion(
        await service.archive_owned(promotion_id, identity.user.id, payload.version)
    )


@router.post(
    "/coupons",
    response_model=CouponResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("coupon:create")],
    responses={**_RESPONSES, 409: {"description": "Coupon conflict"}},
)
async def create_coupon(
    payload: CouponCreateRequest,
    identity: CurrentIdentity,
    service: CouponServiceDependency,
) -> CouponResponse:
    return _coupon(
        await service.create(
            CouponCreate(
                payload.promotion_id,
                payload.code,
                payload.active,
                payload.effective_from,
                payload.effective_until,
                payload.usage_limit,
                payload.per_customer_usage_limit,
                identity.user.id,
            )
        )
    )


@router.get(
    "/coupons",
    response_model=CouponListResponse,
    dependencies=[require_permission("coupon:view")],
    responses=_RESPONSES,
)
async def list_coupons(
    identity: CurrentIdentity,
    service: CouponServiceDependency,
    store_id: UUID | None = None,
    promotion_id: UUID | None = None,
    active: bool | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CouponListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    values, total = await service.list_owned(
        identity.user.id,
        CouponFilter(store_id, promotion_id, active, offset, limit),
    )
    return CouponListResponse(
        items=[_coupon(value) for value in values],
        page=PageMetadata(
            has_more=offset + len(values) < total,
            limit=pagination.limit,
            total=total,
            offset=offset,
        ),
    )


@router.patch(
    "/coupons/{coupon_id}",
    response_model=CouponResponse,
    dependencies=[require_permission("coupon:update")],
    responses={**_RESPONSES, 409: {"description": "Coupon version conflict"}},
)
async def update_coupon(
    coupon_id: UUID,
    payload: CouponUpdateRequest,
    identity: CurrentIdentity,
    service: CouponServiceDependency,
) -> CouponResponse:
    values = payload.model_dump(exclude_unset=True, exclude={"version"})
    return _coupon(
        await service.update_owned(
            coupon_id,
            identity.user.id,
            CouponUpdate(values, payload.version, identity.user.id),
        )
    )


@router.delete(
    "/coupons/{coupon_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("coupon:update")],
    responses={**_RESPONSES, 409: {"description": "Coupon version conflict"}},
)
async def delete_coupon(
    coupon_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: CouponServiceDependency,
) -> Response:
    await service.delete_owned(coupon_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
