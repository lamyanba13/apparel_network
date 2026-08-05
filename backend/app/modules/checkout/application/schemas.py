from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.checkout.domain import CheckoutItem, CheckoutStatus
from app.modules.promotions.domain import PromotionRedemption


@dataclass(frozen=True, slots=True)
class CheckoutCreate:
    cart_id: UUID
    expires_at: datetime | None
    actor_id: UUID
    coupon_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CheckoutConfirm:
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class CheckoutSummary:
    checkout_session_id: UUID
    items: Sequence[CheckoutItem]
    subtotal: Decimal
    discount_total: Decimal
    final_total: Decimal
    currency: str
    quantity: int
    applied_promotions: Sequence[PromotionRedemption]


@dataclass(frozen=True, slots=True)
class CheckoutFilter:
    status: CheckoutStatus | None = None
    offset: int = 0
    limit: int = 25
