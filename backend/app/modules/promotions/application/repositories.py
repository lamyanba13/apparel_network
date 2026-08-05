from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.promotions.application.schemas import CouponFilter, PromotionFilter
from app.modules.promotions.domain import (
    Promotion,
    PromotionCoupon,
    PromotionCustomerUsage,
    PromotionEvent,
    PromotionRedemption,
    PromotionRule,
    PromotionStatus,
)


class PromotionRepository(Protocol):
    async def store_owned(self, store_id: UUID, owner_id: UUID) -> bool: ...
    async def add(self, values: Mapping[str, object]) -> Promotion: ...
    async def get_for_owner(
        self, promotion_id: UUID, owner_id: UUID
    ) -> Promotion | None: ...
    async def list_for_owner(
        self, owner_id: UUID, filters: PromotionFilter
    ) -> tuple[Sequence[Promotion], int]: ...
    async def list_active(
        self, store_id: UUID, at: datetime
    ) -> Sequence[Promotion]: ...
    async def update(
        self,
        promotion_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> Promotion | None: ...
    async def transition(
        self,
        promotion_id: UUID,
        owner_id: UUID,
        *,
        status: PromotionStatus,
        expected_version: int,
        actor_id: UUID,
    ) -> Promotion | None: ...
    async def archive(
        self,
        promotion_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> Promotion | None: ...


class PromotionRuleRepository(Protocol):
    async def add_many(
        self, promotion_id: UUID, values: Sequence[Mapping[str, object]]
    ) -> Sequence[PromotionRule]: ...
    async def list_for_promotions(
        self, promotion_ids: Sequence[UUID]
    ) -> Mapping[UUID, Sequence[PromotionRule]]: ...


class PromotionCouponRepository(Protocol):
    async def add(self, values: Mapping[str, object]) -> PromotionCoupon: ...
    async def code_exists(
        self, store_id: UUID, code: str, exclude_id: UUID | None = None
    ) -> bool: ...
    async def get_for_owner(
        self, coupon_id: UUID, owner_id: UUID
    ) -> PromotionCoupon | None: ...
    async def list_for_owner(
        self, owner_id: UUID, filters: CouponFilter
    ) -> tuple[Sequence[PromotionCoupon], int]: ...
    async def list_by_codes(
        self, store_id: UUID, codes: Sequence[str]
    ) -> Sequence[PromotionCoupon]: ...
    async def update(
        self,
        coupon_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> PromotionCoupon | None: ...
    async def archive(
        self,
        coupon_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> PromotionCoupon | None: ...


class PromotionRedemptionRepository(Protocol):
    async def lock_limits(
        self, promotion_ids: Sequence[UUID], coupon_ids: Sequence[UUID]
    ) -> None: ...
    async def promotion_usage(self, promotion_id: UUID) -> int: ...
    async def coupon_usage(self, coupon_id: UUID) -> int: ...
    async def customer_promotion_usage(
        self, promotion_id: UUID, customer_id: UUID
    ) -> int: ...
    async def customer_usage(
        self, promotion_id: UUID, customer_id: UUID, coupon_id: UUID | None
    ) -> int: ...
    async def completed_order_count(self, customer_id: UUID) -> int: ...
    async def item_contexts(
        self, product_ids: Sequence[UUID]
    ) -> Mapping[UUID, Mapping[str, object]]: ...
    async def add(self, values: Mapping[str, object]) -> PromotionRedemption: ...
    async def increment_usage(
        self,
        promotion_id: UUID,
        coupon_id: UUID | None,
        customer_id: UUID,
        store_id: UUID,
    ) -> PromotionCustomerUsage: ...
    async def link_order(
        self, checkout_session_id: UUID, order_id: UUID, customer_id: UUID
    ) -> Sequence[PromotionRedemption]: ...
    async def list_for_checkout(
        self, checkout_session_id: UUID, customer_id: UUID
    ) -> Sequence[PromotionRedemption]: ...
    async def list_for_order(
        self, order_id: UUID, customer_id: UUID
    ) -> Sequence[PromotionRedemption]: ...


class PromotionOutboxRepository(Protocol):
    async def add(self, event: PromotionEvent) -> None: ...
