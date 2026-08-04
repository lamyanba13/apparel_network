from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.modules.returns.domain import InventoryDisposition, RefundStatus, ReturnStatus


@dataclass(frozen=True, slots=True)
class ReturnItemCreate:
    order_item_id: UUID
    quantity: int


@dataclass(frozen=True, slots=True)
class ReturnCreate:
    order_id: UUID
    shipment_id: UUID
    payment_id: UUID
    reason: str
    items: tuple[ReturnItemCreate, ...]
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ReturnUpdate:
    reason: str
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ReturnTransition:
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ReturnInspection:
    expected_version: int
    dispositions: dict[UUID, InventoryDisposition]
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ReturnFilter:
    store_id: UUID | None = None
    order_id: UUID | None = None
    status: ReturnStatus | None = None
    offset: int = 0
    limit: int = 25


@dataclass(frozen=True, slots=True)
class RefundCreate:
    return_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class RefundTransition:
    expected_version: int
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class RefundFilter:
    return_id: UUID | None = None
    status: RefundStatus | None = None
    offset: int = 0
    limit: int = 25
