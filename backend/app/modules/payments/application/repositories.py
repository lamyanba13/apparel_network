from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.payments.application.schemas import PaymentFilter
from app.modules.payments.domain import (
    PaymentEvent,
    PaymentIntent,
    PaymentStatus,
    PaymentTransaction,
)


class PaymentRepository(Protocol):
    async def get_by_idempotency(
        self, customer_id: UUID, idempotency_key: str
    ) -> PaymentIntent | None: ...

    async def add(self, values: Mapping[str, object]) -> PaymentIntent: ...

    async def list_for_customer(
        self, customer_id: UUID, filters: PaymentFilter
    ) -> tuple[Sequence[PaymentIntent], int]: ...

    async def get_for_customer(
        self, payment_id: UUID, customer_id: UUID
    ) -> PaymentIntent | None: ...

    async def get_for_customer_locked(
        self, payment_id: UUID, customer_id: UUID
    ) -> PaymentIntent | None: ...

    async def transition(
        self,
        payment_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: PaymentStatus,
        transitioned_at: datetime,
        actor_id: UUID,
        archive: bool = False,
    ) -> PaymentIntent | None: ...


class PaymentTransactionRepository(Protocol):
    async def add(self, values: Mapping[str, object]) -> PaymentTransaction: ...

    async def list_for_payment(
        self, payment_id: UUID
    ) -> Sequence[PaymentTransaction]: ...


class PaymentOutboxRepository(Protocol):
    async def add(self, event: PaymentEvent) -> None: ...
