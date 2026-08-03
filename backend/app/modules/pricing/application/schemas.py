from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.pricing.domain import PriceStatus, ProductPrice


@dataclass(frozen=True, slots=True)
class ProductPriceCreate:
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
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ProductPriceUpdate:
    values: Mapping[str, object]
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ProductPriceFilter:
    store_id: UUID | None = None
    product_id: UUID | None = None
    variant_id: UUID | None = None
    currency: str | None = None
    status: PriceStatus | None = None
    effective_at: datetime | None = None
    offset: int = 0
    limit: int = 25


@dataclass(frozen=True, slots=True)
class ProductPriceResponse:
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

    @classmethod
    def from_domain(cls, price: ProductPrice) -> ProductPriceResponse:
        return cls(
            id=price.id,
            store_id=price.store_id,
            product_id=price.product_id,
            variant_id=price.variant_id,
            currency_code=price.currency_code,
            base_price=price.base_price,
            sale_price=price.sale_price,
            compare_at_price=price.compare_at_price,
            cost_price=price.cost_price,
            tax_class=price.tax_class,
            status=price.status,
            effective_from=price.effective_from,
            effective_until=price.effective_until,
            version=price.version,
            created_at=price.created_at,
            updated_at=price.updated_at,
        )
