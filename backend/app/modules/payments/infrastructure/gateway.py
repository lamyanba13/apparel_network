from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.modules.payments.application.gateways import PaymentGatewayResult
from app.modules.payments.domain import PaymentStatus


class NullPaymentGateway:
    """Deterministic provider adapter for the provider-neutral foundation."""

    async def create_intent(
        self,
        *,
        payment_id: UUID,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> PaymentGatewayResult:
        del amount, currency, idempotency_key
        return self._result(payment_id, "created", PaymentStatus.CREATED)

    async def authorize(
        self, *, payment_id: UUID, provider_reference: str
    ) -> PaymentGatewayResult:
        return self._result(
            payment_id, "authorized", PaymentStatus.AUTHORIZED, provider_reference
        )

    async def capture(
        self, *, payment_id: UUID, provider_reference: str
    ) -> PaymentGatewayResult:
        return self._result(
            payment_id, "captured", PaymentStatus.CAPTURED, provider_reference
        )

    async def cancel(
        self, *, payment_id: UUID, provider_reference: str
    ) -> PaymentGatewayResult:
        return self._result(
            payment_id, "cancelled", PaymentStatus.CANCELLED, provider_reference
        )

    async def status(
        self,
        *,
        payment_id: UUID,
        provider_reference: str,
        current_status: PaymentStatus,
    ) -> PaymentGatewayResult:
        return self._result(payment_id, "status", current_status, provider_reference)

    @staticmethod
    def _result(
        payment_id: UUID,
        operation: str,
        status: PaymentStatus,
        provider_reference: str | None = None,
    ) -> PaymentGatewayResult:
        return PaymentGatewayResult(
            provider_reference=provider_reference or f"null-{payment_id}",
            provider_transaction_id=f"null-{operation}-{payment_id}",
            status=status,
            payload={"gateway": "null", "operation": operation},
        )
