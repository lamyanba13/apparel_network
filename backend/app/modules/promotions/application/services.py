from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import cast
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.modules.cart.application.services import CartService
from app.modules.cart.domain import ShoppingCartItem
from app.modules.pricing.domain.currencies import normalize_currency_code
from app.modules.promotions.application.repositories import (
    PromotionCouponRepository,
    PromotionOutboxRepository,
    PromotionRedemptionRepository,
    PromotionRepository,
    PromotionRuleRepository,
)
from app.modules.promotions.application.schemas import (
    CouponCreate,
    CouponFilter,
    CouponUpdate,
    PromotionCreate,
    PromotionEvaluate,
    PromotionFilter,
    PromotionUpdate,
)
from app.modules.promotions.domain import (
    CouponCreated,
    CouponRedeemed,
    DiscountLine,
    Promotion,
    PromotionActivated,
    PromotionApplied,
    PromotionArchived,
    PromotionCoupon,
    PromotionCreated,
    PromotionEvaluation,
    PromotionEvent,
    PromotionRedemption,
    PromotionRemoved,
    PromotionRule,
    PromotionStatus,
    PromotionType,
    PromotionUpdated,
    RejectedPromotion,
    RuleCondition,
)
from app.modules.promotions.domain.policies import calculate_discount
from app.observability.metrics import (
    COUPONS_REDEEMED,
    DISCOUNT_AMOUNT,
    OUTBOX_WRITTEN,
    PROMOTION_RESOLUTION_DURATION,
    PROMOTIONS_ACTIVATED,
    PROMOTIONS_APPLIED,
    PROMOTIONS_CREATED,
)

_COUPON = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")


class PromotionValidationService:
    @staticmethod
    def create(values: PromotionCreate) -> dict[str, object]:
        if values.status is not PromotionStatus.DRAFT:
            raise _validation("status", "Promotions must be created as draft.")
        data = asdict(values)
        data.pop("rules")
        data.pop("actor_id")
        data["name"] = _text(values.name, "name", 2, 150)
        data["description"] = _optional_text(values.description, 2000)
        data["currency"] = (
            normalize_currency_code(values.currency) if values.currency else None
        )
        PromotionValidationService._period(
            values.effective_from, values.effective_until
        )
        PromotionValidationService._numbers(data)
        PromotionValidationService._type(values)
        data["tiers"] = [dict(tier) for tier in values.tiers]
        data["created_by_id"] = values.actor_id
        data["updated_by_id"] = values.actor_id
        return data

    @staticmethod
    def update(values: Mapping[str, object], current: Promotion) -> dict[str, object]:
        allowed = {
            "name",
            "description",
            "currency",
            "percentage",
            "fixed_amount",
            "buy_quantity",
            "get_quantity",
            "bundle_quantity",
            "bundle_price",
            "tiers",
            "public",
            "first_purchase_only",
            "customer_group",
            "minimum_order_amount",
            "minimum_quantity",
            "maximum_discount",
            "usage_limit",
            "per_customer_usage_limit",
            "exclusive",
            "stackable",
            "priority",
            "maximum_stack",
            "effective_from",
            "effective_until",
        }
        if not values or not set(values) <= allowed:
            raise _validation("body", "At least one supported field is required.")
        result = dict(values)
        if "name" in result:
            result["name"] = _text(result["name"], "name", 2, 150)
        if "description" in result:
            result["description"] = _optional_text(result["description"], 2000)
        if "currency" in result and result["currency"] is not None:
            result["currency"] = normalize_currency_code(cast(str, result["currency"]))
        start = cast(
            datetime | None, result.get("effective_from", current.effective_from)
        )
        end = cast(
            datetime | None, result.get("effective_until", current.effective_until)
        )
        PromotionValidationService._period(start, end)
        merged = {**asdict(current), **result}
        PromotionValidationService._numbers(merged)
        PromotionValidationService._type_values(current.promotion_type, merged)
        return result

    @staticmethod
    def _period(start: datetime | None, end: datetime | None) -> None:
        if start is not None and start.utcoffset() is None:
            raise _validation("effective_from", "Timestamp must include a timezone.")
        if end is not None and end.utcoffset() is None:
            raise _validation("effective_until", "Timestamp must include a timezone.")
        if start is not None and end is not None and start >= end:
            raise _validation("effective_until", "End must be after start.")

    @staticmethod
    def _numbers(values: Mapping[str, object]) -> None:
        for field in (
            "percentage",
            "fixed_amount",
            "bundle_price",
            "minimum_order_amount",
            "maximum_discount",
        ):
            value = values.get(field)
            if value is not None and (
                not isinstance(value, Decimal) or not value.is_finite() or value < 0
            ):
                raise _validation(field, "Amount must be finite and non-negative.")
        percentage = values.get("percentage")
        if isinstance(percentage, Decimal) and percentage > 100:
            raise _validation("percentage", "Percentage cannot exceed 100.")
        for field in (
            "buy_quantity",
            "get_quantity",
            "bundle_quantity",
            "minimum_quantity",
            "usage_limit",
            "per_customer_usage_limit",
            "maximum_stack",
        ):
            value = values.get(field)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value <= 0
            ):
                raise _validation(field, "Value must be a positive integer.")
        priority = values.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
            raise _validation("priority", "Priority must be non-negative.")

    @staticmethod
    def _type(values: PromotionCreate) -> None:
        PromotionValidationService._type_values(values.promotion_type, asdict(values))

    @staticmethod
    def _type_values(kind: PromotionType, values: Mapping[str, object]) -> None:
        required = {
            PromotionType.PERCENTAGE: ("percentage",),
            PromotionType.FIXED_AMOUNT: ("fixed_amount", "currency"),
            PromotionType.BUY_X_GET_Y: ("buy_quantity", "get_quantity"),
            PromotionType.BUNDLE: ("bundle_quantity", "bundle_price", "currency"),
            PromotionType.TIER_DISCOUNT: ("tiers",),
            PromotionType.FREE_SHIPPING: (),
        }[kind]
        for field in required:
            if not values.get(field):
                raise _validation(field, f"{field} is required for {kind.value}.")


class PromotionOutboxService:
    def __init__(self, repository: PromotionOutboxRepository) -> None:
        self._repository = repository

    async def write(self, event: PromotionEvent) -> None:
        await self._repository.add(event)
        OUTBOX_WRITTEN.inc()


class PromotionService:
    def __init__(
        self,
        promotions: PromotionRepository,
        rules: PromotionRuleRepository,
        outbox: PromotionOutboxService,
    ) -> None:
        self._promotions = promotions
        self._rules = rules
        self._outbox = outbox
        self._validation = PromotionValidationService()

    async def create(self, values: PromotionCreate) -> Promotion:
        if not await self._promotions.store_owned(values.store_id, values.actor_id):
            raise _not_found()
        promotion = await self._promotions.add(self._validation.create(values))
        await self._rules.add_many(
            promotion.id,
            [
                {
                    "condition": rule.condition,
                    "configuration": dict(rule.configuration),
                    "created_by_id": values.actor_id,
                    "updated_by_id": values.actor_id,
                }
                for rule in values.rules
            ],
        )
        PROMOTIONS_CREATED.inc()
        await self._emit(PromotionCreated, promotion)
        return promotion

    async def list_owned(
        self, owner_id: UUID, filters: PromotionFilter
    ) -> tuple[Sequence[Promotion], int]:
        return await self._promotions.list_for_owner(owner_id, filters)

    async def get_owned(self, promotion_id: UUID, owner_id: UUID) -> Promotion:
        promotion = await self._promotions.get_for_owner(promotion_id, owner_id)
        if promotion is None:
            raise _not_found()
        return promotion

    async def detail_owned(
        self, promotion_id: UUID, owner_id: UUID
    ) -> tuple[Promotion, Sequence[PromotionRule]]:
        promotion = await self.get_owned(promotion_id, owner_id)
        rules = await self._rules.list_for_promotions([promotion.id])
        return promotion, rules.get(promotion.id, ())

    async def update_owned(
        self, promotion_id: UUID, owner_id: UUID, values: PromotionUpdate
    ) -> Promotion:
        current = await self.get_owned(promotion_id, owner_id)
        if current.status is PromotionStatus.ARCHIVED:
            raise _conflict("Archived Promotions cannot be modified.")
        updated = await self._promotions.update(
            promotion_id,
            owner_id,
            values={
                **self._validation.update(values.values, current),
                "updated_by_id": values.actor_id,
            },
            expected_version=values.expected_version,
        )
        if updated is None:
            raise _conflict("The Promotion was modified by another request.")
        await self._emit(PromotionUpdated, updated)
        return updated

    async def activate_owned(
        self, promotion_id: UUID, owner_id: UUID, expected_version: int
    ) -> Promotion:
        current = await self.get_owned(promotion_id, owner_id)
        if current.status is not PromotionStatus.DRAFT:
            raise _conflict("Only draft Promotions can be activated.")
        updated = await self._transition(
            current, owner_id, expected_version, PromotionStatus.ACTIVE
        )
        PROMOTIONS_ACTIVATED.inc()
        await self._emit(PromotionActivated, updated)
        return updated

    async def archive_owned(
        self, promotion_id: UUID, owner_id: UUID, expected_version: int
    ) -> Promotion:
        current = await self.get_owned(promotion_id, owner_id)
        if current.status is PromotionStatus.ARCHIVED:
            raise _conflict("Archived Promotions cannot transition.")
        updated = await self._transition(
            current, owner_id, expected_version, PromotionStatus.ARCHIVED
        )
        await self._emit(PromotionArchived, updated)
        return updated

    async def delete_owned(
        self, promotion_id: UUID, owner_id: UUID, expected_version: int
    ) -> None:
        current = await self.get_owned(promotion_id, owner_id)
        now = datetime.now(UTC)
        archived = await self._promotions.archive(
            promotion_id,
            owner_id,
            expected_version=expected_version,
            deleted_at=now,
            deleted_by_id=owner_id,
        )
        if archived is None:
            raise _conflict("The Promotion was modified by another request.")
        if current.status is not PromotionStatus.ARCHIVED:
            await self._emit(PromotionArchived, archived)
        await self._emit(PromotionRemoved, archived)

    async def _transition(
        self,
        current: Promotion,
        owner_id: UUID,
        expected_version: int,
        status: PromotionStatus,
    ) -> Promotion:
        updated = await self._promotions.transition(
            current.id,
            owner_id,
            status=status,
            expected_version=expected_version,
            actor_id=owner_id,
        )
        if updated is None:
            raise _conflict("The Promotion was modified by another request.")
        return updated

    async def _emit(
        self, event_type: type[PromotionEvent], promotion: Promotion
    ) -> None:
        await self._outbox.write(
            event_type(
                promotion_id=promotion.id,
                store_id=promotion.store_id,
                version=promotion.version,
            )
        )


class CouponService:
    def __init__(
        self,
        coupons: PromotionCouponRepository,
        promotions: PromotionService,
        outbox: PromotionOutboxService,
    ) -> None:
        self._coupons = coupons
        self._promotions = promotions
        self._outbox = outbox

    async def create(self, values: CouponCreate) -> PromotionCoupon:
        promotion = await self._promotions.get_owned(
            values.promotion_id, values.actor_id
        )
        code = self._code(values.code)
        PromotionValidationService._period(
            values.effective_from, values.effective_until
        )
        self._limits(values.usage_limit, values.per_customer_usage_limit)
        if await self._coupons.code_exists(promotion.store_id, code):
            raise _conflict("Coupon code already exists for this Store.")
        coupon = await self._coupons.add(
            {
                "promotion_id": promotion.id,
                "store_id": promotion.store_id,
                "code": code,
                "active": values.active,
                "effective_from": values.effective_from,
                "effective_until": values.effective_until,
                "usage_limit": values.usage_limit,
                "per_customer_usage_limit": values.per_customer_usage_limit,
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        await self._outbox.write(
            CouponCreated(
                promotion_id=promotion.id,
                coupon_id=coupon.id,
                store_id=promotion.store_id,
                version=coupon.version,
            )
        )
        return coupon

    async def list_owned(
        self, owner_id: UUID, filters: CouponFilter
    ) -> tuple[Sequence[PromotionCoupon], int]:
        return await self._coupons.list_for_owner(owner_id, filters)

    async def update_owned(
        self, coupon_id: UUID, owner_id: UUID, values: CouponUpdate
    ) -> PromotionCoupon:
        current = await self._get_owned(coupon_id, owner_id)
        allowed = {
            "code",
            "active",
            "effective_from",
            "effective_until",
            "usage_limit",
            "per_customer_usage_limit",
        }
        if not values.values or not set(values.values) <= allowed:
            raise _validation("body", "At least one supported field is required.")
        changes = dict(values.values)
        if "code" in changes:
            code = self._code(cast(str, changes["code"]))
            if await self._coupons.code_exists(
                current.store_id, code, exclude_id=current.id
            ):
                raise _conflict("Coupon code already exists for this Store.")
            changes["code"] = code
        start = cast(
            datetime | None, changes.get("effective_from", current.effective_from)
        )
        end = cast(
            datetime | None, changes.get("effective_until", current.effective_until)
        )
        PromotionValidationService._period(start, end)
        usage = cast(int | None, changes.get("usage_limit", current.usage_limit))
        per_customer = cast(
            int | None,
            changes.get("per_customer_usage_limit", current.per_customer_usage_limit),
        )
        self._limits(usage, per_customer)
        updated = await self._coupons.update(
            coupon_id,
            owner_id,
            values={**changes, "updated_by_id": values.actor_id},
            expected_version=values.expected_version,
        )
        if updated is None:
            raise _conflict("The Coupon was modified by another request.")
        return updated

    async def delete_owned(
        self, coupon_id: UUID, owner_id: UUID, expected_version: int
    ) -> None:
        await self._get_owned(coupon_id, owner_id)
        if (
            await self._coupons.archive(
                coupon_id,
                owner_id,
                expected_version=expected_version,
                deleted_at=datetime.now(UTC),
                deleted_by_id=owner_id,
            )
            is None
        ):
            raise _conflict("The Coupon was modified by another request.")

    async def _get_owned(self, coupon_id: UUID, owner_id: UUID) -> PromotionCoupon:
        value = await self._coupons.get_for_owner(coupon_id, owner_id)
        if value is None:
            raise _not_found("Coupon")
        return value

    @staticmethod
    def _code(value: str) -> str:
        code = value.strip().upper()
        if not _COUPON.fullmatch(code):
            raise _validation("code", "Coupon code must use 3-64 A-Z characters.")
        return code

    @staticmethod
    def _limits(usage: int | None, per_customer: int | None) -> None:
        for field, value in (
            ("usage_limit", usage),
            ("per_customer_usage_limit", per_customer),
        ):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value <= 0
            ):
                raise _validation(field, "Usage limit must be positive.")
        if usage is not None and per_customer is not None and per_customer > usage:
            raise _validation(
                "per_customer_usage_limit",
                "Per-customer limit cannot exceed total limit.",
            )


@dataclass(frozen=True, slots=True)
class _Candidate:
    promotion: Promotion
    coupon: PromotionCoupon | None
    discount: Decimal


class PromotionEvaluationService:
    def __init__(
        self,
        promotions: PromotionRepository,
        rules: PromotionRuleRepository,
        coupons: PromotionCouponRepository,
        redemptions: PromotionRedemptionRepository,
        carts: CartService,
        outbox: PromotionOutboxService,
    ) -> None:
        self._promotions = promotions
        self._rules = rules
        self._coupons = coupons
        self._redemptions = redemptions
        self._carts = carts
        self._outbox = outbox

    async def evaluate(self, values: PromotionEvaluate) -> PromotionEvaluation:
        started = perf_counter()
        try:
            return await self._evaluate(values)
        finally:
            PROMOTION_RESOLUTION_DURATION.observe(perf_counter() - started)

    async def _evaluate(self, values: PromotionEvaluate) -> PromotionEvaluation:
        cart = await self._carts.get_owned(values.cart_id, values.actor_id)
        summary = await self._carts.summary_owned(cart.id, values.actor_id)
        now = datetime.now(UTC)
        promotions = list(await self._promotions.list_active(cart.store_id, now))
        rules = await self._rules.list_for_promotions(
            [value.id for value in promotions]
        )
        codes = tuple(
            dict.fromkeys(CouponService._code(code) for code in values.coupon_codes)
        )
        coupon_values = await self._coupons.list_by_codes(cart.store_id, codes)
        by_code = {coupon.code: coupon for coupon in coupon_values}
        rejected: list[RejectedPromotion] = [
            RejectedPromotion(None, code, "Coupon code is invalid or unavailable.")
            for code in codes
            if code not in by_code
        ]
        coupon_by_promotion = {coupon.promotion_id: coupon for coupon in coupon_values}
        contexts = await self._redemptions.item_contexts(
            [item.product_id for item in summary.items]
        )
        prior_orders = await self._redemptions.completed_order_count(values.actor_id)
        candidates: list[_Candidate] = []
        for promotion in promotions:
            coupon = coupon_by_promotion.get(promotion.id)
            reason = await self._reject_reason(
                promotion,
                coupon,
                cart.customer_group.value,
                cart.currency,
                summary.subtotal,
                summary.quantity,
                values.actor_id,
                prior_orders,
                now,
            )
            if reason is not None:
                if coupon is not None or promotion.public:
                    rejected.append(
                        RejectedPromotion(
                            promotion.id, coupon.code if coupon else None, reason
                        )
                    )
                continue
            eligible = self._eligible_items(
                summary.items, rules.get(promotion.id, ()), contexts
            )
            if not eligible:
                rejected.append(
                    RejectedPromotion(
                        promotion.id,
                        coupon.code if coupon else None,
                        "Promotion rules did not match any Cart Item.",
                    )
                )
                continue
            eligible_subtotal = sum(
                (item.unit_price * item.quantity for item in eligible), Decimal("0")
            )
            eligible_quantity = sum(item.quantity for item in eligible)
            if (
                promotion.minimum_quantity
                and eligible_quantity < promotion.minimum_quantity
            ):
                rejected.append(
                    RejectedPromotion(
                        promotion.id,
                        coupon.code if coupon else None,
                        "Minimum quantity was not met.",
                    )
                )
                continue
            discount = calculate_discount(
                promotion,
                subtotal=summary.subtotal,
                eligible_subtotal=eligible_subtotal,
                eligible_quantity=eligible_quantity,
                lowest_unit_price=min(item.unit_price for item in eligible),
            )
            if (
                discount <= 0
                and promotion.promotion_type is not PromotionType.FREE_SHIPPING
            ):
                rejected.append(
                    RejectedPromotion(
                        promotion.id,
                        coupon.code if coupon else None,
                        "Promotion produced no discount.",
                    )
                )
                continue
            candidates.append(_Candidate(promotion, coupon, discount))
        selected, stacking_rejections = self._resolve_stacking(candidates)
        rejected.extend(stacking_rejections)
        remaining = summary.subtotal
        lines: list[DiscountLine] = []
        for candidate in selected:
            discount = min(candidate.discount, remaining)
            remaining -= discount
            lines.append(
                DiscountLine(
                    candidate.promotion.id,
                    candidate.coupon.id if candidate.coupon else None,
                    candidate.coupon.code if candidate.coupon else None,
                    candidate.promotion.promotion_type,
                    discount,
                    candidate.promotion.priority,
                )
            )
        discount_total = summary.subtotal - remaining
        return PromotionEvaluation(
            cart_id=cart.id,
            applied_promotions=tuple(lines),
            rejected_promotions=tuple(rejected),
            subtotal=summary.subtotal,
            discount_total=discount_total,
            final_total=summary.subtotal - discount_total,
            currency=summary.currency,
            evaluated_at=now,
        )

    async def freeze_checkout(
        self,
        checkout_session_id: UUID,
        cart_id: UUID,
        customer_id: UUID,
        coupon_codes: tuple[str, ...],
    ) -> PromotionEvaluation:
        cart = await self._carts.get_owned(cart_id, customer_id)
        now = datetime.now(UTC)
        active = await self._promotions.list_active(cart.store_id, now)
        codes = tuple(dict.fromkeys(CouponService._code(code) for code in coupon_codes))
        coupons = await self._coupons.list_by_codes(cart.store_id, codes)
        await self._redemptions.lock_limits(
            [promotion.id for promotion in active],
            [coupon.id for coupon in coupons],
        )
        result = await self.evaluate(
            PromotionEvaluate(cart_id, coupon_codes, customer_id)
        )
        promotions = await self._promotions.list_active(
            cart.store_id, result.evaluated_at
        )
        by_id = {promotion.id: promotion for promotion in promotions}
        for line in result.applied_promotions:
            promotion = by_id[line.promotion_id]
            await self._redemptions.add(
                {
                    "promotion_id": line.promotion_id,
                    "coupon_id": line.coupon_id,
                    "customer_id": customer_id,
                    "store_id": cart.store_id,
                    "cart_id": cart.id,
                    "checkout_session_id": checkout_session_id,
                    "order_id": None,
                    "discount_amount": line.discount_amount,
                    "currency": result.currency,
                    "coupon_code": line.coupon_code,
                    "snapshot": {
                        "promotion_type": line.promotion_type.value,
                        "priority": line.priority,
                        "exclusive": promotion.exclusive,
                        "stackable": promotion.stackable,
                        "promotion_version": promotion.version,
                    },
                    "redeemed_at": result.evaluated_at,
                    "created_by_id": customer_id,
                    "updated_by_id": customer_id,
                }
            )
            await self._redemptions.increment_usage(
                line.promotion_id,
                line.coupon_id,
                customer_id,
                cart.store_id,
            )
            PROMOTIONS_APPLIED.inc()
            DISCOUNT_AMOUNT.labels(result.currency).inc(float(line.discount_amount))
            await self._outbox.write(
                PromotionApplied(
                    promotion_id=line.promotion_id,
                    coupon_id=line.coupon_id,
                    customer_id=customer_id,
                    cart_id=cart.id,
                    checkout_session_id=checkout_session_id,
                    store_id=cart.store_id,
                    version=promotion.version,
                )
            )
            if line.coupon_id is not None:
                COUPONS_REDEEMED.inc()
                await self._outbox.write(
                    CouponRedeemed(
                        promotion_id=line.promotion_id,
                        coupon_id=line.coupon_id,
                        customer_id=customer_id,
                        cart_id=cart.id,
                        checkout_session_id=checkout_session_id,
                        store_id=cart.store_id,
                        version=promotion.version,
                    )
                )
        return result

    async def link_order(
        self, checkout_session_id: UUID, order_id: UUID, customer_id: UUID
    ) -> Sequence[PromotionRedemption]:
        return await self._redemptions.link_order(
            checkout_session_id, order_id, customer_id
        )

    async def checkout_snapshots(
        self, checkout_session_id: UUID, customer_id: UUID
    ) -> Sequence[PromotionRedemption]:
        return await self._redemptions.list_for_checkout(
            checkout_session_id, customer_id
        )

    async def order_snapshots(
        self, order_id: UUID, customer_id: UUID
    ) -> Sequence[PromotionRedemption]:
        return await self._redemptions.list_for_order(order_id, customer_id)

    async def _reject_reason(
        self,
        promotion: Promotion,
        coupon: PromotionCoupon | None,
        customer_group: str,
        currency: str,
        subtotal: Decimal,
        quantity: int,
        customer_id: UUID,
        prior_orders: int,
        now: datetime,
    ) -> str | None:
        if not promotion.public and coupon is None:
            return "A coupon code is required."
        if promotion.currency is not None and promotion.currency != currency:
            return "Promotion currency does not match the Cart."
        if promotion.customer_group and promotion.customer_group != customer_group:
            return "Customer group is not eligible."
        if promotion.first_purchase_only and prior_orders > 0:
            return "Promotion is limited to the first purchase."
        if promotion.minimum_order_amount and subtotal < promotion.minimum_order_amount:
            return "Minimum order amount was not met."
        if promotion.minimum_quantity and quantity < promotion.minimum_quantity:
            return "Minimum quantity was not met."
        if (
            promotion.usage_limit is not None
            and await self._redemptions.promotion_usage(promotion.id)
            >= promotion.usage_limit
        ):
            return "Promotion usage limit was reached."
        if promotion.per_customer_usage_limit is not None and (
            await self._redemptions.customer_promotion_usage(promotion.id, customer_id)
            >= promotion.per_customer_usage_limit
        ):
            return "Per-customer usage limit was reached."
        if coupon is not None:
            if not coupon.active:
                return "Coupon is inactive."
            if coupon.effective_from and coupon.effective_from > now:
                return "Coupon is not active yet."
            if coupon.effective_until and coupon.effective_until <= now:
                return "Coupon has expired."
            total = await self._redemptions.customer_usage(
                promotion.id, customer_id, coupon.id
            )
            if (
                coupon.per_customer_usage_limit is not None
                and total >= coupon.per_customer_usage_limit
            ):
                return "Coupon per-customer usage limit was reached."
            if coupon.usage_limit is not None and (
                await self._redemptions.coupon_usage(coupon.id) >= coupon.usage_limit
            ):
                return "Coupon usage limit was reached."
        return None

    @staticmethod
    def _eligible_items(
        items: Sequence[ShoppingCartItem],
        rules: Sequence[PromotionRule],
        contexts: Mapping[UUID, Mapping[str, object]],
    ) -> list[ShoppingCartItem]:
        eligible: list[ShoppingCartItem] = []
        for item in items:
            context = contexts.get(item.product_id, {})
            matched = True
            for rule in rules:
                target = rule.configuration.get("id") or rule.configuration.get("value")
                if rule.condition is RuleCondition.PRODUCT:
                    matched = str(item.product_id) == str(target)
                elif rule.condition is RuleCondition.VARIANT:
                    matched = str(item.variant_id) == str(target)
                elif rule.condition is RuleCondition.CATALOG:
                    matched = str(context.get("catalog_id")) == str(target)
                elif rule.condition is RuleCondition.BRAND:
                    matched = (
                        str(context.get("brand", "")).casefold()
                        == str(target).casefold()
                    )
                elif rule.condition is RuleCondition.CATEGORY:
                    matched = str(target) in {
                        str(value)
                        for value in cast(
                            Sequence[UUID], context.get("category_ids", ())
                        )
                    }
                if not matched:
                    break
            if matched:
                eligible.append(item)
        return eligible

    @staticmethod
    def _resolve_stacking(
        candidates: Sequence[_Candidate],
    ) -> tuple[list[_Candidate], list[RejectedPromotion]]:
        ordered = sorted(
            candidates,
            key=lambda value: (-value.promotion.priority, str(value.promotion.id)),
        )
        rejected: list[RejectedPromotion] = []
        if not ordered:
            return [], rejected
        exclusive = next(
            (value for value in ordered if value.promotion.exclusive), None
        )
        if exclusive is not None:
            for candidate in ordered:
                if candidate is not exclusive:
                    rejected.append(
                        RejectedPromotion(
                            candidate.promotion.id,
                            candidate.coupon.code if candidate.coupon else None,
                            "A higher-priority exclusive Promotion was selected.",
                        )
                    )
            return [exclusive], rejected
        selected: list[_Candidate] = []
        limit = min(
            (
                value.promotion.maximum_stack
                for value in ordered
                if value.promotion.maximum_stack is not None
            ),
            default=len(ordered),
        )
        for candidate in ordered:
            if len(selected) >= limit or (
                selected and not candidate.promotion.stackable
            ):
                rejected.append(
                    RejectedPromotion(
                        candidate.promotion.id,
                        candidate.coupon.code if candidate.coupon else None,
                        "Promotion stacking policy excluded this Promotion.",
                    )
                )
            else:
                selected.append(candidate)
        return selected, rejected


def _text(value: object, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise _validation(field, f"{field} must be text.")
    normalized = " ".join(value.split())
    if not minimum <= len(normalized) <= maximum:
        raise _validation(
            field, f"{field} must contain {minimum}-{maximum} characters."
        )
    return normalized


def _optional_text(value: object, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum:
        raise _validation(
            "description", f"Description cannot exceed {maximum} characters."
        )
    return " ".join(value.split()) or None


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Promotion validation failed",
        detail="Promotion fields are invalid.",
        status_code=422,
        errors=[FieldError(field=field, code="invalid_promotion", message=message)],
    )


def _not_found(subject: str = "Promotion") -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title=f"{subject} not found",
        detail=f"The requested {subject} was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Promotion conflict",
        detail=detail,
        status_code=409,
    )
