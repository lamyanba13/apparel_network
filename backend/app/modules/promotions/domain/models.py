from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import JsonValue


class PromotionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class PromotionType(StrEnum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"
    BUY_X_GET_Y = "buy_x_get_y"
    BUNDLE = "bundle"
    TIER_DISCOUNT = "tier_discount"
    FREE_SHIPPING = "free_shipping"


class RuleCondition(StrEnum):
    CATEGORY = "category"
    BRAND = "brand"
    CATALOG = "catalog"
    PRODUCT = "product"
    VARIANT = "variant"


@dataclass(frozen=True, slots=True)
class Promotion:
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
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class PromotionRule:
    id: UUID
    promotion_id: UUID
    condition: RuleCondition
    configuration: dict[str, JsonValue]
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class PromotionCoupon:
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
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class PromotionRedemption:
    id: UUID
    promotion_id: UUID
    coupon_id: UUID | None
    customer_id: UUID
    store_id: UUID
    cart_id: UUID
    checkout_session_id: UUID
    order_id: UUID | None
    discount_amount: Decimal
    currency: str
    coupon_code: str | None
    snapshot: dict[str, JsonValue]
    redeemed_at: datetime
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class PromotionCustomerUsage:
    id: UUID
    promotion_id: UUID
    coupon_id: UUID | None
    customer_id: UUID
    store_id: UUID
    usage_count: int
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class DiscountLine:
    promotion_id: UUID
    coupon_id: UUID | None
    coupon_code: str | None
    promotion_type: PromotionType
    discount_amount: Decimal
    priority: int


@dataclass(frozen=True, slots=True)
class RejectedPromotion:
    promotion_id: UUID | None
    coupon_code: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class PromotionEvaluation:
    cart_id: UUID
    applied_promotions: tuple[DiscountLine, ...]
    rejected_promotions: tuple[RejectedPromotion, ...]
    subtotal: Decimal
    discount_total: Decimal
    final_total: Decimal
    currency: str
    evaluated_at: datetime
