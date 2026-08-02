from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.products.domain import ProductStatus, ProductVisibility


class ProductCreateRequest(BaseModel):
    catalog_id: UUID
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(max_length=180, examples=["linen-shirt"])
    short_description: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    status: ProductStatus = ProductStatus.DRAFT
    visibility: ProductVisibility = ProductVisibility.PRIVATE
    sku: str = Field(max_length=64, examples=["LN-SHIRT-001"])
    brand: str | None = Field(default=None, max_length=150)
    sort_order: int = Field(default=0, ge=0)


class ProductUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    slug: str | None = Field(default=None, max_length=180)
    short_description: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    visibility: ProductVisibility | None = None
    sku: str | None = Field(default=None, max_length=64)
    brand: str | None = Field(default=None, max_length=150)
    sort_order: int | None = Field(default=None, ge=0)
    version: int = Field(ge=1)


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
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
    version: int


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    page: PageMetadata


class ProductVariantCreateRequest(BaseModel):
    reference: str = Field(max_length=64, examples=["LN-SHIRT-NAVY-M"])
    attributes: dict[str, str] = Field(min_length=1, max_length=12)
    sort_order: int = Field(default=0, ge=0)


class ProductVariantUpdateRequest(BaseModel):
    reference: str | None = Field(default=None, max_length=64)
    attributes: dict[str, str] | None = Field(default=None, min_length=1, max_length=12)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    version: int = Field(ge=1)


class ProductVariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID
    store_id: UUID
    reference: str
    attributes: dict[str, str]
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    version: int
