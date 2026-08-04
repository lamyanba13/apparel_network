from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class CartEvent:
    cart_id: UUID
    user_id: UUID
    store_id: UUID
    version: int
    item_id: UUID | None = None
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "cart_id": str(self.cart_id),
            "user_id": str(self.user_id),
            "store_id": str(self.store_id),
            "item_id": str(self.item_id) if self.item_id else None,
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CartCreated(CartEvent):
    event_name: ClassVar[str] = "cart.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class CartUpdated(CartEvent):
    event_name: ClassVar[str] = "cart.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class CartDeleted(CartEvent):
    event_name: ClassVar[str] = "cart.deleted"


@dataclass(frozen=True, slots=True, kw_only=True)
class CartCheckedOut(CartEvent):
    event_name: ClassVar[str] = "cart.checked_out"


@dataclass(frozen=True, slots=True, kw_only=True)
class CartExpired(CartEvent):
    event_name: ClassVar[str] = "cart.expired"


@dataclass(frozen=True, slots=True, kw_only=True)
class CartItemAdded(CartEvent):
    event_name: ClassVar[str] = "cart.item_added"


@dataclass(frozen=True, slots=True, kw_only=True)
class CartItemUpdated(CartEvent):
    event_name: ClassVar[str] = "cart.item_updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class CartItemRemoved(CartEvent):
    event_name: ClassVar[str] = "cart.item_removed"
