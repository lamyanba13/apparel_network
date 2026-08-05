from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.common.pagination import PageMetadata
from app.modules.promotions.domain import (
    PromotionStatus,
    PromotionType,
    RuleCondition,
)


class RuleRequest(BaseModel):
    condition: RuleCondition
    configuration: dict[str, JsonValue]


class PromotionCreateRequest(BaseModel):
    store_id: UUID
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    promotion_type: PromotionType
    status: PromotionStatus = PromotionStatus.DRAFT
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    percentage: Decimal | None = None
    fixed_amount: Decimal | None = None
    buy_quantity: int | None = Field(default=None, gt=0)
    get_quantity: int | None = Field(default=None, gt=0)
    bundle_quantity: int | None = Field(default=None, gt=0)
    bundle_price: Decimal | None = None
    tiers: list[dict[str, JsonValue]] = Field(default_factory=list)
    public: bool = True
    first_purchase_only: bool = False
    customer_group: str | None = Field(default=None, max_length=50)
    minimum_order_amount: Decimal | None = None
    minimum_quantity: int | None = Field(default=None, gt=0)
    maximum_discount: Decimal | None = None
    usage_limit: int | None = Field(default=None, gt=0)
    per_customer_usage_limit: int | None = Field(default=None, gt=0)
    exclusive: bool = False
    stackable: bool = True
    priority: int = Field(default=0, ge=0)
    maximum_stack: int | None = Field(default=None, gt=0)
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    rules: list[RuleRequest] = Field(default_factory=list)


class PromotionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    percentage: Decimal | None = None
    fixed_amount: Decimal | None = None
    buy_quantity: int | None = Field(default=None, gt=0)
    get_quantity: int | None = Field(default=None, gt=0)
    bundle_quantity: int | None = Field(default=None, gt=0)
    bundle_price: Decimal | None = None
    tiers: list[dict[str, JsonValue]] | None = None
    public: bool | None = None
    first_purchase_only: bool | None = None
    customer_group: str | None = Field(default=None, max_length=50)
    minimum_order_amount: Decimal | None = None
    minimum_quantity: int | None = Field(default=None, gt=0)
    maximum_discount: Decimal | None = None
    usage_limit: int | None = Field(default=None, gt=0)
    per_customer_usage_limit: int | None = Field(default=None, gt=0)
    exclusive: bool | None = None
    stackable: bool | None = None
    priority: int | None = Field(default=None, ge=0)
    maximum_stack: int | None = Field(default=None, gt=0)
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def has_changes(self) -> PromotionUpdateRequest:
        if not self.model_fields_set - {"version"}:
            raise ValueError("at least one promotion field is required")
        return self


class LifecycleRequest(BaseModel):
    version: int = Field(ge=1)


class PromotionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    store_id: UUID
    name: str
    description: str | None
    promotion_type: PromotionType
    status: PromotionStatus
    currency: str | None
    percentage: Decimal | None
    fixed_amount: Decimal | None
    buy_quantity: int | None
    get_quantity: int | None
    bundle_quantity: int | None
    bundle_price: Decimal | None
    tiers: tuple[dict[str, JsonValue], ...]
    public: bool
    first_purchase_only: bool
    customer_group: str | None
    minimum_order_amount: Decimal | None
    minimum_quantity: int | None
    maximum_discount: Decimal | None
    usage_limit: int | None
    per_customer_usage_limit: int | None
    exclusive: bool
    stackable: bool
    priority: int
    maximum_stack: int | None
    effective_from: datetime | None
    effective_until: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class PromotionRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    promotion_id: UUID
    condition: RuleCondition
    configuration: dict[str, JsonValue]
    version: int


class PromotionDetailResponse(PromotionResponse):
    rules: list[PromotionRuleResponse]


class PromotionListResponse(BaseModel):
    items: list[PromotionResponse]
    page: PageMetadata


class CouponCreateRequest(BaseModel):
    promotion_id: UUID
    code: str = Field(min_length=3, max_length=64)
    active: bool = True
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    usage_limit: int | None = Field(default=None, gt=0)
    per_customer_usage_limit: int | None = Field(default=None, gt=0)


class CouponUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=3, max_length=64)
    active: bool | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    usage_limit: int | None = Field(default=None, gt=0)
    per_customer_usage_limit: int | None = Field(default=None, gt=0)
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def has_changes(self) -> CouponUpdateRequest:
        if not self.model_fields_set - {"version"}:
            raise ValueError("at least one coupon field is required")
        return self


class CouponResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    promotion_id: UUID
    store_id: UUID
    code: str
    active: bool
    effective_from: datetime | None
    effective_until: datetime | None
    usage_limit: int | None
    per_customer_usage_limit: int | None
    version: int
    created_at: datetime
    updated_at: datetime


class CouponListResponse(BaseModel):
    items: list[CouponResponse]
    page: PageMetadata


class PromotionEvaluateRequest(BaseModel):
    cart_id: UUID
    coupon_codes: list[str] = Field(default_factory=list, max_length=20)


class DiscountLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    promotion_id: UUID
    coupon_id: UUID | None
    coupon_code: str | None
    promotion_type: PromotionType
    discount_amount: Decimal
    priority: int


class RejectedPromotionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    promotion_id: UUID | None
    coupon_code: str | None
    reason: str


class PromotionEvaluateResponse(BaseModel):
    cart_id: UUID
    applied_promotions: list[DiscountLineResponse]
    rejected_promotions: list[RejectedPromotionResponse]
    discount_breakdown: list[DiscountLineResponse]
    subtotal: Decimal
    discount_total: Decimal
    final_total: Decimal
    currency: str
    evaluated_at: datetime
