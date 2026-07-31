from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.stores.domain import StoreStatus, VerificationStatus


class StoreCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    phone: str = Field(min_length=7, max_length=32)
    email: str = Field(min_length=3, max_length=320)
    website: str | None = Field(default=None, max_length=2048)
    address: str = Field(min_length=1, max_length=300)
    city: str = Field(min_length=1, max_length=100)
    district: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=3, max_length=20)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    logo_url: str | None = Field(default=None, max_length=2048)
    banner_url: str | None = Field(default=None, max_length=2048)


class StoreUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    website: str | None = Field(default=None, max_length=2048)
    address: str | None = Field(default=None, min_length=1, max_length=300)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    district: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    country: str | None = Field(default=None, min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, min_length=3, max_length=20)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    logo_url: str | None = Field(default=None, max_length=2048)
    banner_url: str | None = Field(default=None, max_length=2048)


class StoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    owner_id: UUID
    name: str
    slug: str
    description: str | None
    phone: str
    email: str
    website: str | None
    address: str
    city: str
    district: str
    state: str
    country: str
    postal_code: str
    latitude: Decimal | None
    longitude: Decimal | None
    logo_url: str | None
    banner_url: str | None
    status: StoreStatus
    verification_status: VerificationStatus
    created_at: datetime
    updated_at: datetime
    version: int


class StoreListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StoreResponse]
    page: PageMetadata
