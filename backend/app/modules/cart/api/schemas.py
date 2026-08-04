from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.common.pagination import PageMetadata
from app.modules.cart.domain import CartStatus
from app.modules.pricing.domain import CustomerGroup


class CartCreateRequest(BaseModel):
    store_id: UUID
    currency: str = Field(default="INR", min_length=3, max_length=3)
    customer_group: CustomerGroup = CustomerGroup.PUBLIC
    expires_at: datetime | None = None


class CartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    store_id: UUID
    status: CartStatus
    currency: str
    customer_group: CustomerGroup
    expires_at: datetime
    checked_out_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class CartListResponse(BaseModel):
    items: list[CartResponse]
    page: PageMetadata


class CartItemCreateRequest(BaseModel):
    variant_id: UUID
    quantity: int = Field(gt=0)
    version: int = Field(ge=1, description="Current Cart version")


class CartItemUpdateRequest(BaseModel):
    quantity: int = Field(gt=0)
    version: int = Field(ge=1, description="Current Cart Item version")


class CartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cart_id: UUID
    product_id: UUID
    variant_id: UUID
    quantity: int
    price_snapshot_id: UUID
    unit_price: Decimal
    currency: str
    inventory_snapshot: dict[str, JsonValue]
    added_at: datetime
    updated_at: datetime
    version: int


class CartSummaryResponse(BaseModel):
    cart_id: UUID
    items: list[CartItemResponse]
    subtotal: Decimal
    currency: str
    quantity: int
