from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class ReturnEvent:
    return_id: UUID
    order_id: UUID
    customer_id: UUID
    store_id: UUID
    version: int
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_name: ClassVar[str]

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "return_id": str(self.return_id),
            "order_id": str(self.order_id),
            "customer_id": str(self.customer_id),
            "store_id": str(self.store_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ReturnRequested(ReturnEvent):
    event_name: ClassVar[str] = "return.requested"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReturnApproved(ReturnEvent):
    event_name: ClassVar[str] = "return.approved"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReturnReceived(ReturnEvent):
    event_name: ClassVar[str] = "return.received"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReturnInspected(ReturnEvent):
    event_name: ClassVar[str] = "return.inspected"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReturnRejected(ReturnEvent):
    event_name: ClassVar[str] = "return.rejected"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReturnCancelled(ReturnEvent):
    event_name: ClassVar[str] = "return.cancelled"


@dataclass(frozen=True, slots=True, kw_only=True)
class RefundEvent:
    refund_id: UUID
    return_id: UUID
    payment_id: UUID
    customer_id: UUID
    store_id: UUID
    version: int
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_name: ClassVar[str]

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "refund_id": str(self.refund_id),
            "return_id": str(self.return_id),
            "payment_id": str(self.payment_id),
            "customer_id": str(self.customer_id),
            "store_id": str(self.store_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RefundCreated(RefundEvent):
    event_name: ClassVar[str] = "refund.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class RefundCompleted(RefundEvent):
    event_name: ClassVar[str] = "refund.completed"


@dataclass(frozen=True, slots=True, kw_only=True)
class RefundFailed(RefundEvent):
    event_name: ClassVar[str] = "refund.failed"
