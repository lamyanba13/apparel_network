from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.pricing.domain import PriceStatus


class ProductPriceCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "store_id": "018f0f7e-8b8f-7b2d-a3e6-4c1d6b3a9a10",
                    "product_id": "018f0f7e-8b8f-7b2d-a3e6-4c1d6b3a9a11",
                    "variant_id": "018f0f7e-8b8f-7b2d-a3e6-4c1d6b3a9a12",
                    "currency_code": "INR",
                    "base_price": "1999.00",
                    "sale_price": "1499.00",
                    "compare_at_price": "2499.00",
                    "tax_class": "standard",
                    "status": "draft",
                }
            ]
        }
    )
    store_id: UUID
    product_id: UUID
    variant_id: UUID | None = None
    currency_code: str = Field(min_length=3, max_length=3)
    base_price: Decimal = Field(ge=0, max_digits=19, decimal_places=4)
    sale_price: Decimal | None = Field(
        default=None, ge=0, max_digits=19, decimal_places=4
    )
    compare_at_price: Decimal | None = Field(
        default=None, ge=0, max_digits=19, decimal_places=4
    )
    cost_price: Decimal | None = Field(
        default=None, ge=0, max_digits=19, decimal_places=4
    )
    tax_class: str = Field(default="standard", min_length=1, max_length=50)
    status: PriceStatus = PriceStatus.DRAFT
    effective_from: datetime | None = None
    effective_until: datetime | None = None


class ProductPriceUpdateRequest(BaseModel):
    base_price: Decimal | None = Field(
        default=None, ge=0, max_digits=19, decimal_places=4
    )
    sale_price: Decimal | None = Field(
        default=None, ge=0, max_digits=19, decimal_places=4
    )
    compare_at_price: Decimal | None = Field(
        default=None, ge=0, max_digits=19, decimal_places=4
    )
    cost_price: Decimal | None = Field(
        default=None, ge=0, max_digits=19, decimal_places=4
    )
    tax_class: str | None = Field(default=None, min_length=1, max_length=50)
    status: PriceStatus | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    version: int = Field(ge=1)


class ProductPriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    store_id: UUID
    product_id: UUID
    variant_id: UUID | None
    currency_code: str
    base_price: Decimal
    sale_price: Decimal | None
    compare_at_price: Decimal | None
    cost_price: Decimal | None
    tax_class: str
    status: PriceStatus
    effective_from: datetime | None
    effective_until: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class ProductPriceListResponse(BaseModel):
    items: list[ProductPriceResponse]
    page: PageMetadata
