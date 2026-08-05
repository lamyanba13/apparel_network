from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.orders.domain import OrderItem, OrderStatus
from app.modules.promotions.domain import PromotionRedemption


@dataclass(frozen=True, slots=True)
class OrderCreate:
    checkout_session_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class OrderConfirm:
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class OrderSummary:
    order_id: UUID
    items: Sequence[OrderItem]
    subtotal: Decimal
    discount_total: Decimal
    final_total: Decimal
    currency: str
    quantity: int
    applied_promotions: Sequence[PromotionRedemption]


@dataclass(frozen=True, slots=True)
class OrderFilter:
    store_id: UUID | None = None
    status: OrderStatus | None = None
    offset: int = 0
    limit: int = 25
