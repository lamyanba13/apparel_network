from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.cart.domain import CartStatus, ShoppingCartItem
from app.modules.pricing.domain import CustomerGroup


@dataclass(frozen=True, slots=True)
class CartCreate:
    store_id: UUID
    currency: str
    customer_group: CustomerGroup
    expires_at: datetime | None
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class CartItemCreate:
    variant_id: UUID
    quantity: int
    expected_cart_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class CartItemUpdate:
    quantity: int
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class CartFilter:
    store_id: UUID | None = None
    status: CartStatus | None = None
    offset: int = 0
    limit: int = 25


@dataclass(frozen=True, slots=True)
class CartSummary:
    cart_id: UUID
    items: Sequence[ShoppingCartItem]
    subtotal: Decimal
    currency: str
    quantity: int
