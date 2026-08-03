from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import cast
from uuid import UUID

from app.modules.pricing.domain.currencies import normalize_currency_code

_MAX_AMOUNT = Decimal("999999999999999.9999")


class PriceStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class PriceListStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class CustomerGroup(StrEnum):
    PUBLIC = "public"
    WHOLESALE = "wholesale"
    VIP = "vip"
    STAFF = "staff"
    CUSTOM = "custom"


class ResolutionLevel(StrEnum):
    VARIANT = "variant"
    PRODUCT = "product"
    DEFAULT_STORE = "default_store"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency_code: str

    def __post_init__(self) -> None:
        normalized = normalize_currency_code(self.currency_code)
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


@dataclass(frozen=True, slots=True)
class PriceList:
    id: UUID
    store_id: UUID
    name: str
    slug: str
    description: str | None
    currency_code: str
    priority: int
    status: PriceListStatus
    customer_group: CustomerGroup
    effective_from: datetime | None
    effective_until: datetime | None
    is_default: bool
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class PriceAssignment:
    id: UUID
    price_list_id: UUID
    price_id: UUID
    version: int
    created_at: datetime
    created_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class ResolvedPrice:
    price_id: UUID
    price_list_id: UUID | None
    store_id: UUID
    product_id: UUID
    variant_id: UUID | None
    currency_code: str
    customer_group: CustomerGroup
    amount: Decimal
    base_price: Decimal
    sale_price: Decimal | None
    tax_class: str
    resolution_level: ResolutionLevel
    price_version: int
    resolved_at: datetime
