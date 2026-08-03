from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.pricing.domain import CustomerGroup, PriceListStatus


@dataclass(frozen=True, slots=True)
class PriceListCreate:
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
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class PriceListUpdate:
    values: Mapping[str, object]
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class PriceListFilter:
    store_id: UUID | None = None
    currency: str | None = None
    status: PriceListStatus | None = None
    customer_group: CustomerGroup | None = None
    effective_at: datetime | None = None
    offset: int = 0
    limit: int = 25


@dataclass(frozen=True, slots=True)
class AssignPriceRequest:
    price_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ResolvePriceRequest:
    store_id: UUID
    product_id: UUID
    variant_id: UUID | None
    currency: str
    customer_group: CustomerGroup
    timestamp: datetime
    actor_id: UUID
