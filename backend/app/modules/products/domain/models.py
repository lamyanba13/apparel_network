from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ProductVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    HIDDEN = "hidden"


@dataclass(frozen=True, slots=True)
class Product:
    id: UUID
    catalog_id: UUID
    store_id: UUID
    name: str
    slug: str
    short_description: str | None
    description: str | None
    status: ProductStatus
    visibility: ProductVisibility
    sku: str
    brand: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    version: int
    created_by_id: UUID | None
    updated_by_id: UUID | None
