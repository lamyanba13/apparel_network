from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import JsonValue

from app.modules.pricing.domain.currencies import normalize_currency_code


class PaymentProvider(StrEnum):
    NULL = "null"


class PaymentStatus(StrEnum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentTransactionType(StrEnum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not self.amount.is_finite() or self.amount < 0:
            raise ValueError("payment amount must be finite and non-negative")
        object.__setattr__(self, "currency", normalize_currency_code(self.currency))


@dataclass(frozen=True, slots=True)
class PaymentSnapshot:
    order_id: UUID
    customer_id: UUID
    store_id: UUID
    money: Money


@dataclass(frozen=True, slots=True)
class PaymentIntent:
    id: UUID
    order_id: UUID
    customer_id: UUID
    store_id: UUID
    provider: PaymentProvider
    provider_reference: str
    status: PaymentStatus
    currency: str
    amount: Decimal
    idempotency_key: str
    expires_at: datetime
    authorized_at: datetime | None
    captured_at: datetime | None
    failed_at: datetime | None
    cancelled_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None
    deleted_at: datetime | None
    deleted_by_id: UUID | None


@dataclass(frozen=True, slots=True)
class PaymentTransaction:
    id: UUID
    payment_intent_id: UUID
    provider_transaction_id: str
    event_type: PaymentTransactionType
    status: PaymentStatus
    amount: Decimal
    currency: str
    provider_payload: dict[str, JsonValue]
    occurred_at: datetime
    created_at: datetime
