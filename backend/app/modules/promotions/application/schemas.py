from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.promotions.domain import (
    PromotionStatus,
    PromotionType,
    RuleCondition,
)


@dataclass(frozen=True, slots=True)
class RuleCreate:
    condition: RuleCondition
    configuration: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PromotionCreate:
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
    tiers: tuple[Mapping[str, object], ...]
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
    rules: tuple[RuleCreate, ...]
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class PromotionUpdate:
    values: Mapping[str, object]
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class PromotionFilter:
    store_id: UUID | None = None
    status: PromotionStatus | None = None
    promotion_type: PromotionType | None = None
    offset: int = 0
    limit: int = 25


@dataclass(frozen=True, slots=True)
class CouponCreate:
    promotion_id: UUID
    code: str
    active: bool
    effective_from: datetime | None
    effective_until: datetime | None
    usage_limit: int | None
    per_customer_usage_limit: int | None
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class CouponUpdate:
    values: Mapping[str, object]
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class CouponFilter:
    store_id: UUID | None = None
    promotion_id: UUID | None = None
    active: bool | None = None
    offset: int = 0
    limit: int = 25


@dataclass(frozen=True, slots=True)
class PromotionEvaluate:
    cart_id: UUID
    coupon_codes: tuple[str, ...]
    actor_id: UUID
