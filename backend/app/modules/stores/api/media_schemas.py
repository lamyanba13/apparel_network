from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.stores.domain import StoreMediaStatus, StoreMediaType


class StoreMediaUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    display_order: int | None = Field(default=None, ge=0)
    is_public: bool | None = None


class StoreMediaReorderItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_id: UUID
    display_order: int = Field(ge=0)
    version: int = Field(ge=1)


class StoreMediaReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StoreMediaReorderItemRequest] = Field(
        min_length=1,
        max_length=100,
    )


class StoreMediaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    store_id: UUID
    uploaded_by_id: UUID
    media_type: StoreMediaType
    status: StoreMediaStatus
    original_filename: str
    extension: str
    mime_type: str
    file_size: int
    width: int
    height: int
    orientation: int
    aspect_ratio: Decimal
    display_order: int
    is_public: bool
    created_at: datetime
    updated_at: datetime
    version: int
    download_url: str
    download_url_expires_at: datetime


class StoreMediaListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StoreMediaResponse]
    page: PageMetadata
