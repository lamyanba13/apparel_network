from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.modules.promotions.domain.models import Promotion, PromotionType

_QUANTUM = Decimal("0.0001")


def calculate_discount(
    promotion: Promotion,
    *,
    subtotal: Decimal,
    eligible_subtotal: Decimal,
    eligible_quantity: int,
    lowest_unit_price: Decimal,
) -> Decimal:
    """Calculate one deterministic, currency-preserving promotion discount."""
    discount = Decimal("0")
    if promotion.promotion_type is PromotionType.PERCENTAGE:
        discount = eligible_subtotal * (promotion.percentage or Decimal("0")) / 100
    elif promotion.promotion_type is PromotionType.FIXED_AMOUNT:
        discount = promotion.fixed_amount or Decimal("0")
    elif promotion.promotion_type is PromotionType.BUY_X_GET_Y:
        buy = promotion.buy_quantity or 0
        get = promotion.get_quantity or 0
        group = buy + get
        if group > 0:
            discount = lowest_unit_price * get * (eligible_quantity // group)
    elif promotion.promotion_type is PromotionType.BUNDLE:
        size = promotion.bundle_quantity or 0
        if size > 0:
            bundles = eligible_quantity // size
            regular = lowest_unit_price * size
            discount = max(
                Decimal("0"),
                (regular - (promotion.bundle_price or regular)) * bundles,
            )
    elif promotion.promotion_type is PromotionType.TIER_DISCOUNT:
        percentage = Decimal("0")
        for tier in promotion.tiers:
            raw_minimum = tier.get("minimum_quantity", 0)
            minimum = (
                raw_minimum
                if isinstance(raw_minimum, int) and not isinstance(raw_minimum, bool)
                else 0
            )
            if eligible_quantity >= minimum:
                percentage = Decimal(str(tier.get("percentage", "0")))
        discount = eligible_subtotal * percentage / 100
    elif promotion.promotion_type is PromotionType.FREE_SHIPPING:
        discount = Decimal("0")
    if promotion.maximum_discount is not None:
        discount = min(discount, promotion.maximum_discount)
    return min(subtotal, max(Decimal("0"), discount)).quantize(
        _QUANTUM, rounding=ROUND_HALF_UP
    )
