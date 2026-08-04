from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.modules.returns.application.gateways import RefundGatewayResult
from app.modules.returns.domain import RefundStatus


class NullRefundGateway:
    """Deterministic provider adapter with no external financial side effects."""

    async def create_refund(
        self,
        *,
        refund_id: UUID,
        payment_reference: str,
        amount: Decimal,
        currency: str,
    ) -> RefundGatewayResult:
        del payment_reference, amount, currency
        return self._result(refund_id, "processing", RefundStatus.PROCESSING)

    async def status(
        self,
        *,
        refund_id: UUID,
        provider_reference: str,
        current_status: RefundStatus,
    ) -> RefundGatewayResult:
        del current_status
        return self._result(
            refund_id, "completed", RefundStatus.COMPLETED, provider_reference
        )

    @staticmethod
    def _result(
        refund_id: UUID,
        operation: str,
        status: RefundStatus,
        provider_reference: str | None = None,
    ) -> RefundGatewayResult:
        return RefundGatewayResult(
            provider_reference=provider_reference or f"null-refund-{refund_id}",
            provider_transaction_id=f"null-{operation}-{refund_id}",
            status=status,
            payload={"gateway": "null", "operation": operation},
        )
