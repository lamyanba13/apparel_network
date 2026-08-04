from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.modules.returns.application.schemas import RefundFilter, ReturnFilter
from app.modules.returns.domain import (
    InventoryDisposition,
    ProductReturn,
    Refund,
    RefundEvent,
    RefundStatus,
    RefundTransaction,
    ReturnEvent,
    ReturnItem,
    ReturnStatus,
)


class ReturnRepository(Protocol):
    async def add(self, values: Mapping[str, object]) -> ProductReturn: ...
    async def get_for_customer(
        self, return_id: UUID, customer_id: UUID
    ) -> ProductReturn | None: ...
    async def list_for_customer(
        self, customer_id: UUID, filters: ReturnFilter
    ) -> tuple[Sequence[ProductReturn], int]: ...
    async def update_reason(
        self,
        return_id: UUID,
        customer_id: UUID,
        *,
        reason: str,
        expected_version: int,
        actor_id: UUID,
    ) -> ProductReturn | None: ...
    async def transition(
        self,
        return_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: ReturnStatus,
        transitioned_at: datetime,
        actor_id: UUID,
        archive: bool = False,
    ) -> ProductReturn | None: ...


class ReturnItemRepository(Protocol):
    async def add_many(
        self, values: Sequence[Mapping[str, object]]
    ) -> Sequence[ReturnItem]: ...
    async def list_for_return(self, return_id: UUID) -> Sequence[ReturnItem]: ...
    async def committed_quantity(self, order_item_id: UUID) -> int: ...
    async def inspect(
        self,
        return_id: UUID,
        dispositions: Mapping[UUID, InventoryDisposition],
        inspected_at: datetime,
    ) -> Sequence[ReturnItem]: ...


class RefundRepository(Protocol):
    async def add(self, values: Mapping[str, object]) -> Refund: ...
    async def get_for_return(self, return_id: UUID) -> Refund | None: ...
    async def get_for_customer(
        self, refund_id: UUID, customer_id: UUID
    ) -> Refund | None: ...
    async def list_for_customer(
        self, customer_id: UUID, filters: RefundFilter
    ) -> tuple[Sequence[Refund], int]: ...
    async def completed_amount(self, payment_id: UUID) -> Decimal: ...
    async def transition(
        self,
        refund_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: RefundStatus,
        provider_reference: str | None,
        transitioned_at: datetime,
        actor_id: UUID,
    ) -> Refund | None: ...


class RefundTransactionRepository(Protocol):
    async def add(self, values: Mapping[str, object]) -> RefundTransaction: ...
    async def list_for_refund(self, refund_id: UUID) -> Sequence[RefundTransaction]: ...


class ReturnOutboxRepository(Protocol):
    async def add(self, event: ReturnEvent | RefundEvent) -> None: ...
