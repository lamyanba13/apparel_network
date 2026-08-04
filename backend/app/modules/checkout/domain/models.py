from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.modules.pricing.domain.currencies import normalize_currency_code


class CheckoutStatus(StrEnum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not self.amount.is_finite() or self.amount < 0:
            raise ValueError("money amount must be finite and non-negative")
        object.__setattr__(self, "currency", normalize_currency_code(self.currency))


@dataclass(frozen=True, slots=True)
class CheckoutSnapshot:
    price_id: UUID
    money: Money
    inventory_id: UUID
    inventory_version: int
    price_snapshot_time: datetime
    inventory_snapshot_time: datetime

    def __post_init__(self) -> None:
        if self.inventory_version < 1:
            raise ValueError("inventory version must be positive")
        if self.price_snapshot_time.utcoffset() is None:
            raise ValueError("price snapshot time must be timezone-aware")
        if self.inventory_snapshot_time.utcoffset() is None:
            raise ValueError("inventory snapshot time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    id: UUID
    cart_id: UUID
    user_id: UUID
    store_id: UUID
    status: CheckoutStatus
    currency: str
    subtotal: Decimal
    expires_at: datetime
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class CheckoutItem:
    id: UUID
    checkout_session_id: UUID
    product_id: UUID
    variant_id: UUID
    quantity: int
    price_id: UUID
    unit_price: Decimal
    currency: str
    inventory_id: UUID
    inventory_version: int
    price_snapshot_time: datetime
    inventory_snapshot_time: datetime
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
