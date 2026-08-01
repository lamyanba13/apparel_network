from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from app.modules.catalogs.domain import CatalogStatus, CatalogVisibility


@dataclass(frozen=True, slots=True)
class CatalogCreate:
    store_id: UUID
    name: str
    slug: str
    description: str | None
    status: CatalogStatus
    visibility: CatalogVisibility
    sort_order: int
    actor_id: UUID
    is_default: bool


@dataclass(frozen=True, slots=True)
class CatalogUpdate:
    values: Mapping[str, object]
    expected_version: int
    actor_id: UUID
