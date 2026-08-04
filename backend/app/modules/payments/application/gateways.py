from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue

from app.modules.payments.domain import PaymentStatus


@dataclass(frozen=True, slots=True)
class PaymentGatewayResult:
    provider_reference: str
    provider_transaction_id: str
    status: PaymentStatus
    payload: dict[str, JsonValue]


class PaymentGateway(Protocol):
    async def create_intent(
        self,
        *,
        payment_id: UUID,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> PaymentGatewayResult: ...

    async def authorize(
        self, *, payment_id: UUID, provider_reference: str
    ) -> PaymentGatewayResult: ...

    async def capture(
        self, *, payment_id: UUID, provider_reference: str
    ) -> PaymentGatewayResult: ...

    async def cancel(
        self, *, payment_id: UUID, provider_reference: str
    ) -> PaymentGatewayResult: ...

    async def status(
        self,
        *,
        payment_id: UUID,
        provider_reference: str,
        current_status: PaymentStatus,
    ) -> PaymentGatewayResult: ...
