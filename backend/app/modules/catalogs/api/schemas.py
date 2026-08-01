from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.catalogs.domain import CatalogStatus, CatalogVisibility


class CatalogCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "store_id": "018f0f7e-8b8f-7b2d-a3e6-4c1d6b3a9a10",
                    "name": "Summer Collection",
                    "slug": "summer-collection",
                    "description": "Seasonal arrivals",
                    "status": "draft",
                    "visibility": "public",
                    "sort_order": 0,
                    "is_default": False,
                }
            ]
        }
    )
    store_id: UUID
    name: str = Field(min_length=2, max_length=150)
    slug: str = Field(max_length=180, examples=["summer-collection"])
    description: str | None = Field(default=None, max_length=2000)
    status: CatalogStatus = CatalogStatus.DRAFT
    visibility: CatalogVisibility = CatalogVisibility.PRIVATE
    sort_order: int = Field(default=0, ge=0)
    is_default: bool = False


class CatalogUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    slug: str | None = Field(default=None, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    visibility: CatalogVisibility | None = None
    sort_order: int | None = Field(default=None, ge=0)
    is_default: bool | None = None
    version: int = Field(ge=1)


class CatalogResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "018f0f7e-8b8f-7b2d-a3e6-4c1d6b3a9a11",
                    "store_id": "018f0f7e-8b8f-7b2d-a3e6-4c1d6b3a9a10",
                    "name": "Summer Collection",
                    "slug": "summer-collection",
                    "status": "draft",
                    "visibility": "public",
                    "sort_order": 0,
                    "is_default": False,
                    "version": 1,
                }
            ]
        },
    )

    id: UUID
    store_id: UUID
    name: str
    slug: str
    description: str | None
    status: CatalogStatus
    visibility: CatalogVisibility
    sort_order: int
    created_at: datetime
    updated_at: datetime
    version: int
    activated_at: datetime | None
    archived_at: datetime | None
    is_default: bool


class CatalogListResponse(BaseModel):
    items: list[CatalogResponse]
    page: PageMetadata
