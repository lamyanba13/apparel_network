from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CatalogStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class CatalogVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    HIDDEN = "hidden"


@dataclass(frozen=True, slots=True)
class Catalog:
    id: UUID
    store_id: UUID
    name: str
    slug: str
    description: str | None
    status: CatalogStatus
    visibility: CatalogVisibility
    sort_order: int
    activated_at: datetime | None
    archived_at: datetime | None
    is_default: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    version: int
    created_by_id: UUID | None
    updated_by_id: UUID | None
