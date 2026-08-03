from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.pricing.domain import (
    CustomerGroup,
    PriceListStatus,
    ResolutionLevel,
)


class PriceListCreateRequest(BaseModel):
    store_id: UUID
    name: str = Field(min_length=2, max_length=150)
    slug: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    currency_code: str = Field(min_length=3, max_length=3)
    priority: int = Field(default=0, ge=0, le=1_000_000)
    status: PriceListStatus = PriceListStatus.DRAFT
    customer_group: CustomerGroup = CustomerGroup.PUBLIC
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    is_default: bool = False


class PriceListUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    slug: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    priority: int | None = Field(default=None, ge=0, le=1_000_000)
    status: PriceListStatus | None = None
    customer_group: CustomerGroup | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    is_default: bool | None = None
    version: int = Field(ge=1)


class PriceListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    store_id: UUID
    name: str
    slug: str
    description: str | None
    currency_code: str
    priority: int
    status: PriceListStatus
    customer_group: CustomerGroup
    effective_from: datetime | None
    effective_until: datetime | None
    is_default: bool
    version: int
    created_at: datetime
    updated_at: datetime


class PriceListPageResponse(BaseModel):
    items: list[PriceListResponse]
    page: PageMetadata


class AssignPriceRequest(BaseModel):
    price_id: UUID


class PriceAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    price_list_id: UUID
    price_id: UUID
    version: int
    created_at: datetime


class ResolvedPriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    price_id: UUID
    price_list_id: UUID | None
    store_id: UUID
    product_id: UUID
    variant_id: UUID | None
    currency_code: str
    customer_group: CustomerGroup
    amount: Decimal
    base_price: Decimal
    sale_price: Decimal | None
    tax_class: str
    resolution_level: ResolutionLevel
    price_version: int
    resolved_at: datetime
