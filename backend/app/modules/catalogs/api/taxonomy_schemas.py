from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.catalogs.domain.taxonomy import (
    CategoryStatus,
    CollectionStatus,
    CollectionType,
    Visibility,
)


class CategoryCreateRequest(BaseModel):
    store_id: UUID
    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(min_length=1, max_length=180)
    description: str | None = None
    parent_category_id: UUID | None = None
    sort_order: int = Field(default=0, ge=0)
    status: CategoryStatus = CategoryStatus.DRAFT
    visibility: Visibility = Visibility.PRIVATE


class CategoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    slug: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    parent_category_id: UUID | None = None
    sort_order: int | None = Field(default=None, ge=0)
    status: CategoryStatus | None = None
    visibility: Visibility | None = None


class CollectionCreateRequest(BaseModel):
    store_id: UUID
    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(min_length=1, max_length=180)
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)
    status: CollectionStatus = CollectionStatus.DRAFT
    collection_type: CollectionType = CollectionType.MANUAL
    visibility: Visibility = Visibility.PRIVATE


class CollectionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    slug: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    sort_order: int | None = Field(default=None, ge=0)
    status: CollectionStatus | None = None
    collection_type: CollectionType | None = None
    visibility: Visibility | None = None


class ReorderRequest(BaseModel):
    version: int = Field(ge=1)
    product_ids: list[UUID]
