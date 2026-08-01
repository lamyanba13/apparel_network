from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.common.pagination import PageMetadata


class StoreSearchResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: UUID
    name: str
    slug: str
    description: str | None
    category: str | None
    city: str
    state: str
    country: str
    postal_code: str
    latitude: Decimal | None
    longitude: Decimal | None
    verified: bool
    active: bool
    currently_open: bool
    logo_exists: bool
    banner_exists: bool
    media_count: int
    created_at: datetime
    updated_at: datetime
    score: float | None = None


class StoreAutocompleteItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: UUID
    name: str
    slug: str


class StoreSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StoreSearchResultResponse]
    page: PageMetadata
    processing_time_ms: int | None = None


class StoreAutocompleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StoreAutocompleteItemResponse]


class SearchRebuildResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: str
