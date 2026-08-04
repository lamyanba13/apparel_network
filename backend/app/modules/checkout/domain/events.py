from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckoutEvent:
    checkout_id: UUID
    cart_id: UUID
    user_id: UUID
    store_id: UUID
    version: int
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "checkout_id": str(self.checkout_id),
            "cart_id": str(self.cart_id),
            "user_id": str(self.user_id),
            "store_id": str(self.store_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckoutCreated(CheckoutEvent):
    event_name: ClassVar[str] = "checkout.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckoutConfirmed(CheckoutEvent):
    event_name: ClassVar[str] = "checkout.confirmed"


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckoutExpired(CheckoutEvent):
    event_name: ClassVar[str] = "checkout.expired"


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckoutCancelled(CheckoutEvent):
    event_name: ClassVar[str] = "checkout.cancelled"
