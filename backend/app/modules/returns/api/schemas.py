from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.returns.domain import (
    InventoryDisposition,
    RefundStatus,
    RefundTransactionType,
    ReturnStatus,
)


class ReturnItemCreateRequest(BaseModel):
    order_item_id: UUID
    quantity: int = Field(gt=0)


class ReturnCreateRequest(BaseModel):
    order_id: UUID
    shipment_id: UUID
    payment_id: UUID
    reason: str = Field(min_length=1, max_length=1000)
    items: list[ReturnItemCreateRequest] = Field(min_length=1, max_length=100)


class ReturnUpdateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    version: int = Field(ge=1)


class LifecycleRequest(BaseModel):
    version: int = Field(ge=1)


class DispositionRequest(BaseModel):
    return_item_id: UUID
    disposition: InventoryDisposition


class ReturnInspectionRequest(BaseModel):
    version: int = Field(ge=1)
    dispositions: list[DispositionRequest] = Field(min_length=1, max_length=100)


class ReturnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    shipment_id: UUID
    payment_id: UUID
    customer_id: UUID
    store_id: UUID
    status: ReturnStatus
    reason: str
    requested_at: datetime
    approved_at: datetime | None
    received_at: datetime | None
    inspected_at: datetime | None
    rejected_at: datetime | None
    cancelled_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class ReturnItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    return_id: UUID
    order_item_id: UUID
    variant_id: UUID
    inventory_item_id: UUID
    quantity: int
    unit_price: Decimal
    currency: str
    disposition: InventoryDisposition
    inspected_at: datetime | None
    created_at: datetime


class ReturnDetailResponse(ReturnResponse):
    items: list[ReturnItemResponse]


class ReturnListResponse(BaseModel):
    items: list[ReturnResponse]
    page: PageMetadata


class ReturnSummaryResponse(BaseModel):
    return_id: UUID
    status: ReturnStatus
    item_quantity: int
    refundable_amount: Decimal
    currency: str
    dispositions: dict[InventoryDisposition, int]


class RefundCreateRequest(BaseModel):
    return_id: UUID


class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    return_id: UUID
    payment_id: UUID
    customer_id: UUID
    store_id: UUID
    status: RefundStatus
    amount: Decimal
    currency: str
    provider: str
    provider_reference: str | None
    completed_at: datetime | None
    failed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class RefundTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    refund_id: UUID
    provider_transaction_id: str
    event_type: RefundTransactionType
    status: RefundStatus
    occurred_at: datetime
    created_at: datetime


class RefundDetailResponse(RefundResponse):
    transactions: list[RefundTransactionResponse]


class RefundListResponse(BaseModel):
    items: list[RefundResponse]
    page: PageMetadata


class RefundStatusResponse(BaseModel):
    refund_id: UUID
    status: RefundStatus
    checked_at: datetime
