from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import JsonValue

from app.modules.pricing.domain.currencies import normalize_currency_code
from app.modules.pricing.domain.models import CustomerGroup


class CartStatus(StrEnum):
    ACTIVE = "active"
    CHECKED_OUT = "checked_out"
    ABANDONED = "abandoned"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class Quantity:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or self.value <= 0:
            raise ValueError("quantity must be a positive integer")


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    price_id: UUID
    amount: Decimal
    currency: str
    resolved_at: datetime

    def __post_init__(self) -> None:
        if not self.amount.is_finite() or self.amount < 0:
            raise ValueError("snapshot amount must be finite and non-negative")
        if self.resolved_at.utcoffset() is None:
            raise ValueError("snapshot timestamp must be timezone-aware")
        object.__setattr__(self, "currency", normalize_currency_code(self.currency))


@dataclass(frozen=True, slots=True)
class ShoppingCart:
    id: UUID
    user_id: UUID
    store_id: UUID
    status: CartStatus
    currency: str
    customer_group: CustomerGroup
    expires_at: datetime
    checked_out_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class ShoppingCartItem:
    id: UUID
    cart_id: UUID
    product_id: UUID
    variant_id: UUID
    quantity: int
    price_snapshot_id: UUID
    unit_price: Decimal
    currency: str
    inventory_snapshot: Mapping[str, JsonValue]
    added_at: datetime
    updated_at: datetime
    version: int
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None
