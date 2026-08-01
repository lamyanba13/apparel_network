from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CategoryStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class CollectionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class CollectionType(StrEnum):
    MANUAL = "manual"
    SMART = "smart"
    SEASONAL = "seasonal"
    FEATURED = "featured"


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    HIDDEN = "hidden"


@dataclass(frozen=True, slots=True)
class Category:
    id: UUID
    store_id: UUID
    name: str
    slug: str
    description: str | None
    parent_category_id: UUID | None
    sort_order: int
    status: CategoryStatus
    visibility: Visibility
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    version: int
    created_by_id: UUID | None
    updated_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class Collection:
    id: UUID
    store_id: UUID
    name: str
    slug: str
    description: str | None
    sort_order: int
    status: CollectionStatus
    visibility: Visibility
    collection_type: CollectionType
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    version: int
    created_by_id: UUID | None
    updated_by_id: UUID | None
