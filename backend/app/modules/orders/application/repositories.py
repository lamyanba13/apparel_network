from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.orders.application.schemas import OrderFilter
from app.modules.orders.domain import Order, OrderEvent, OrderItem, OrderStatus


class OrderRepository(Protocol):
    async def next_number_value(self) -> int: ...

    async def exists_for_checkout(self, checkout_id: UUID) -> bool: ...

    async def add(self, values: Mapping[str, object]) -> Order: ...

    async def list_for_customer(
        self, customer_id: UUID, filters: OrderFilter
    ) -> tuple[Sequence[Order], int]: ...

    async def get_for_customer(
        self, order_id: UUID, customer_id: UUID
    ) -> Order | None: ...

    async def transition(
        self,
        order_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: OrderStatus,
        transitioned_at: datetime,
        actor_id: UUID,
    ) -> Order | None: ...

    async def archive(
        self,
        order_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> Order | None: ...


class OrderItemRepository(Protocol):
    async def add_many(
        self, values: Sequence[Mapping[str, object]]
    ) -> Sequence[OrderItem]: ...

    async def list_for_order(self, order_id: UUID) -> Sequence[OrderItem]: ...

    async def list_for_order_locked(self, order_id: UUID) -> Sequence[OrderItem]: ...


class OrderOutboxRepository(Protocol):
    async def add(self, event: OrderEvent) -> None: ...
