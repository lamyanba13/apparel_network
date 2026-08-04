from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import JsonValue


class ReturnStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    RECEIVED = "received"
    INSPECTED = "inspected"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class InventoryDisposition(StrEnum):
    RESTOCK = "restock"
    DAMAGED = "damaged"
    INSPECTION_REQUIRED = "inspection_required"
    DISPOSE = "dispose"


class RefundStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RefundTransactionType(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProductReturn:
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
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class ReturnItem:
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


@dataclass(frozen=True, slots=True)
class Refund:
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
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class RefundTransaction:
    id: UUID
    refund_id: UUID
    provider_transaction_id: str
    event_type: RefundTransactionType
    status: RefundStatus
    provider_payload: dict[str, JsonValue]
    occurred_at: datetime
    created_at: datetime
