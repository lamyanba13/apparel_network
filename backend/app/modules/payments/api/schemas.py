from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.payments.domain import (
    PaymentProvider,
    PaymentStatus,
    PaymentTransactionType,
)


class PaymentCreateRequest(BaseModel):
    order_id: UUID


class PaymentTransitionRequest(BaseModel):
    version: int = Field(ge=1, description="Current Payment version")


class PaymentIntentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    customer_id: UUID
    store_id: UUID
    provider: PaymentProvider
    provider_reference: str
    status: PaymentStatus
    currency: str
    amount: Decimal
    expires_at: datetime
    authorized_at: datetime | None
    captured_at: datetime | None
    failed_at: datetime | None
    cancelled_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class PaymentListResponse(BaseModel):
    items: list[PaymentIntentResponse]
    page: PageMetadata


class PaymentTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_intent_id: UUID
    provider_transaction_id: str
    event_type: PaymentTransactionType
    status: PaymentStatus
    amount: Decimal
    currency: str
    occurred_at: datetime
    created_at: datetime


class PaymentDetailResponse(PaymentIntentResponse):
    transactions: list[PaymentTransactionResponse]


class PaymentStatusResponse(BaseModel):
    payment_id: UUID
    provider: PaymentProvider
    provider_reference: str
    status: PaymentStatus
    checked_at: datetime
