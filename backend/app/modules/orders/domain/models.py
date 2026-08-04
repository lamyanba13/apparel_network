from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.modules.pricing.domain.currencies import normalize_currency_code

_ORDER_NUMBER_PATTERN = re.compile(r"^ORD-[0-9]{8}-[0-9]{6}$")


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
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
class OrderNumber:
    value: str

    def __post_init__(self) -> None:
        if not _ORDER_NUMBER_PATTERN.fullmatch(self.value):
            raise ValueError("order number must use ORD-YYYYMMDD-000001 format")

    @classmethod
    def create(cls, placed_on: date, sequence_value: int) -> OrderNumber:
        if not 1 <= sequence_value <= 999_999:
            raise ValueError("order number sequence is outside the supported range")
        return cls(f"ORD-{placed_on:%Y%m%d}-{sequence_value:06d}")


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    price_id: UUID
    money: Money
    inventory_id: UUID
    inventory_version: int
    snapshot_timestamp: datetime

    def __post_init__(self) -> None:
        if self.inventory_version < 1:
            raise ValueError("inventory version must be positive")
        if self.snapshot_timestamp.utcoffset() is None:
            raise ValueError("snapshot timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Order:
    id: UUID
    checkout_session_id: UUID
    cart_id: UUID
    store_id: UUID
    customer_id: UUID
    order_number: str
    status: OrderStatus
    currency: str
    subtotal: Decimal
    placed_at: datetime
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class OrderItem:
    id: UUID
    order_id: UUID
    product_id: UUID
    variant_id: UUID
    quantity: int
    price_id: UUID
    unit_price: Decimal
    currency: str
    inventory_id: UUID
    inventory_version: int
    snapshot_timestamp: datetime
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
