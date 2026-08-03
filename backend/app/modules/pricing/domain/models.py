from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import cast
from uuid import UUID

_CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")
_MAX_AMOUNT = Decimal("999999999999999.9999")


class PriceStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency_code: str

    def __post_init__(self) -> None:
        normalized = self.currency_code.strip().upper()
        if not _CURRENCY_CODE.fullmatch(normalized):
            raise ValueError("currency_code must be a three-letter uppercase code")
        if not self.amount.is_finite() or self.amount < 0 or self.amount > _MAX_AMOUNT:
            raise ValueError("money amount must be finite, non-negative, and supported")
        if cast(int, self.amount.as_tuple().exponent) < -4:
            raise ValueError("money amount cannot exceed four decimal places")
        object.__setattr__(self, "currency_code", normalized)


@dataclass(frozen=True, slots=True)
class ProductPrice:
    id: UUID
    store_id: UUID
    product_id: UUID
    variant_id: UUID | None
    currency_code: str
    base_price: Decimal
    sale_price: Decimal | None
    compare_at_price: Decimal | None
    cost_price: Decimal | None
    tax_class: str
    status: PriceStatus
    effective_from: datetime | None
    effective_until: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None
