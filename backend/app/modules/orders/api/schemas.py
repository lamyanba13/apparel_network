from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.orders.domain import OrderStatus


class OrderCreateRequest(BaseModel):
    checkout_session_id: UUID


class OrderConfirmRequest(BaseModel):
    version: int = Field(ge=1, description="Current Order version")


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    checkout_session_id: UUID
    cart_id: UUID
    store_id: UUID
    customer_id: UUID
    order_number: str
    status: OrderStatus
    currency: str
    subtotal: Decimal
    placed_at: datetime
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: PageMetadata


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    product_id: UUID
    variant_id: UUID
    quantity: int
    price_id: UUID
    unit_price: Decimal
    currency: str
    inventory_id: UUID
    inventory_version: int
    snapshot_timestamp: datetime
    version: int
    created_at: datetime
    updated_at: datetime


class OrderSummaryResponse(BaseModel):
    order_id: UUID
    items: list[OrderItemResponse]
    subtotal: Decimal
    currency: str
    quantity: int
