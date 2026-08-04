from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderEvent:
    order_id: UUID
    checkout_session_id: UUID
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
            "order_id": str(self.order_id),
            "checkout_session_id": str(self.checkout_session_id),
            "customer_id": str(self.customer_id),
            "store_id": str(self.store_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderCreated(OrderEvent):
    event_name: ClassVar[str] = "order.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderConfirmed(OrderEvent):
    event_name: ClassVar[str] = "order.confirmed"


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderCancelled(OrderEvent):
    event_name: ClassVar[str] = "order.cancelled"
