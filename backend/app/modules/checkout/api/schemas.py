from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.checkout.domain import CheckoutStatus


class CheckoutCreateRequest(BaseModel):
    cart_id: UUID
    expires_at: datetime | None = None


class CheckoutConfirmRequest(BaseModel):
    version: int = Field(ge=1, description="Current Checkout Session version")


class CheckoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cart_id: UUID
    user_id: UUID
    store_id: UUID
    status: CheckoutStatus
    currency: str
    subtotal: Decimal
    expires_at: datetime
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class CheckoutListResponse(BaseModel):
    items: list[CheckoutResponse]
    page: PageMetadata


class CheckoutItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    checkout_session_id: UUID
    product_id: UUID
    variant_id: UUID
    quantity: int
    price_id: UUID
    unit_price: Decimal
    currency: str
    inventory_id: UUID
    inventory_version: int
    price_snapshot_time: datetime
    inventory_snapshot_time: datetime
    version: int
    created_at: datetime
    updated_at: datetime


class CheckoutSummaryResponse(BaseModel):
    checkout_session_id: UUID
    items: list[CheckoutItemResponse]
    subtotal: Decimal
    currency: str
    quantity: int
