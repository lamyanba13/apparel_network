from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.modules.payments.domain import PaymentProvider, PaymentStatus


@dataclass(frozen=True, slots=True)
class PaymentCreate:
    order_id: UUID
    customer_id: UUID
    idempotency_key: str
    provider: PaymentProvider = PaymentProvider.NULL


@dataclass(frozen=True, slots=True)
class PaymentTransition:
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class PaymentFilter:
    store_id: UUID | None = None
    order_id: UUID | None = None
    status: PaymentStatus | None = None
    offset: int = 0
    limit: int = 25
