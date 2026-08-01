from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from app.modules.products.domain import ProductStatus, ProductVisibility


@dataclass(frozen=True, slots=True)
class ProductCreate:
    catalog_id: UUID
    name: str
    slug: str
    short_description: str | None
    description: str | None
    status: ProductStatus
    visibility: ProductVisibility
    sku: str
    brand: str | None
    sort_order: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ProductUpdate:
    values: Mapping[str, object]
    expected_version: int
    actor_id: UUID
