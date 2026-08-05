from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class PromotionEvent:
    promotion_id: UUID
    store_id: UUID
    version: int
    coupon_id: UUID | None = None
    customer_id: UUID | None = None
    cart_id: UUID | None = None
    checkout_session_id: UUID | None = None
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_name: ClassVar[str]

    @property
    def payload(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "promotion_id": str(self.promotion_id),
            "store_id": str(self.store_id),
            "version": self.version,
            "timestamp": self.occurred_at.isoformat(),
        }
        for key, value in (
            ("coupon_id", self.coupon_id),
            ("customer_id", self.customer_id),
            ("cart_id", self.cart_id),
            ("checkout_session_id", self.checkout_session_id),
        ):
            if value is not None:
                payload[key] = str(value)
        return payload


@dataclass(frozen=True, slots=True, kw_only=True)
class PromotionCreated(PromotionEvent):
    event_name: ClassVar[str] = "promotion.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class PromotionUpdated(PromotionEvent):
    event_name: ClassVar[str] = "promotion.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class PromotionActivated(PromotionEvent):
    event_name: ClassVar[str] = "promotion.activated"


@dataclass(frozen=True, slots=True, kw_only=True)
class PromotionArchived(PromotionEvent):
    event_name: ClassVar[str] = "promotion.archived"


@dataclass(frozen=True, slots=True, kw_only=True)
class CouponCreated(PromotionEvent):
    event_name: ClassVar[str] = "coupon.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class CouponRedeemed(PromotionEvent):
    event_name: ClassVar[str] = "coupon.redeemed"


@dataclass(frozen=True, slots=True, kw_only=True)
class PromotionApplied(PromotionEvent):
    event_name: ClassVar[str] = "promotion.applied"


@dataclass(frozen=True, slots=True, kw_only=True)
class PromotionRemoved(PromotionEvent):
    event_name: ClassVar[str] = "promotion.removed"
