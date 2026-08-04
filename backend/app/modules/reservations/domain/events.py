from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class ReservationEvent:
    reservation_id: UUID
    order_id: UUID
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
            "reservation_id": str(self.reservation_id),
            "order_id": str(self.order_id),
            "payment_id": str(self.payment_id),
            "customer_id": str(self.customer_id),
            "store_id": str(self.store_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ReservationCreated(ReservationEvent):
    event_name: ClassVar[str] = "reservation.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReservationActivated(ReservationEvent):
    event_name: ClassVar[str] = "reservation.activated"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReservationReleased(ReservationEvent):
    event_name: ClassVar[str] = "reservation.released"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReservationExpired(ReservationEvent):
    event_name: ClassVar[str] = "reservation.expired"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReservationConsumed(ReservationEvent):
    event_name: ClassVar[str] = "reservation.consumed"
