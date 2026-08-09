from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.ingestion.domain import ImportSourceType, ImportStatus


@dataclass(frozen=True, slots=True)
class CatalogImportCreate:
    store_id: UUID
    catalog_id: UUID
    actor_id: UUID
    source_type: ImportSourceType
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class CatalogImportFilter:
    store_id: UUID | None = None
    status: ImportStatus | None = None
    source_type: ImportSourceType | None = None
    offset: int = 0
    limit: int = 25


@dataclass(frozen=True, slots=True)
class ProductMatch:
    id: UUID
    catalog_id: UUID
    name: str
    slug: str
    description: str | None
    brand: str | None
    version: int


@dataclass(frozen=True, slots=True)
class VariantMatch:
    id: UUID
    product_id: UUID
    reference: str
    attributes: dict[str, str]
    version: int


@dataclass(frozen=True, slots=True)
class PriceMatch:
    id: UUID
    base_price: Decimal
    version: int


@dataclass(frozen=True, slots=True)
class InventoryMatch:
    id: UUID
    quantity_on_hand: int
    version: int


@dataclass(frozen=True, slots=True)
class PreviewSummary:
    total_rows: int
    valid_rows: int
    invalid_rows: int
    error_count: int
    warning_count: int
