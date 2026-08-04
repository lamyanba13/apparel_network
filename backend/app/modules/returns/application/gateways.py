from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue

from app.modules.returns.domain import RefundStatus


@dataclass(frozen=True, slots=True)
class RefundGatewayResult:
    provider_reference: str
    provider_transaction_id: str
    status: RefundStatus
    payload: dict[str, JsonValue]


class RefundGateway(Protocol):
    async def create_refund(
        self,
        *,
        refund_id: UUID,
        payment_reference: str,
        amount: Decimal,
        currency: str,
    ) -> RefundGatewayResult: ...

    async def status(
        self,
        *,
        refund_id: UUID,
        provider_reference: str,
        current_status: RefundStatus,
    ) -> RefundGatewayResult: ...
