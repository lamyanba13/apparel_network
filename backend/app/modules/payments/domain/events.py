from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentEvent:
    payment_id: UUID
    order_id: UUID
    customer_id: UUID
    store_id: UUID
    version: int
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "payment_id": str(self.payment_id),
            "order_id": str(self.order_id),
            "customer_id": str(self.customer_id),
            "store_id": str(self.store_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentCreated(PaymentEvent):
    event_name: ClassVar[str] = "payment.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentAuthorized(PaymentEvent):
    event_name: ClassVar[str] = "payment.authorized"


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentCaptured(PaymentEvent):
    event_name: ClassVar[str] = "payment.captured"


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentFailed(PaymentEvent):
    event_name: ClassVar[str] = "payment.failed"


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentCancelled(PaymentEvent):
    event_name: ClassVar[str] = "payment.cancelled"
