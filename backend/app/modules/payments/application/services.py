from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from uuid6 import uuid7

from app.common.errors import ErrorCode
from app.common.exceptions import AppError
from app.modules.orders.application.schemas import OrderConfirm
from app.modules.orders.application.services import OrderService
from app.modules.orders.domain import OrderStatus
from app.modules.payments.application.gateways import (
    PaymentGateway,
    PaymentGatewayResult,
)
from app.modules.payments.application.repositories import (
    PaymentOutboxRepository,
    PaymentRepository,
    PaymentTransactionRepository,
)
from app.modules.payments.application.schemas import (
    PaymentCreate,
    PaymentFilter,
    PaymentTransition,
)
from app.modules.payments.domain import (
    Money,
    PaymentAuthorized,
    PaymentCancelled,
    PaymentCaptured,
    PaymentCreated,
    PaymentEvent,
    PaymentFailed,
    PaymentIntent,
    PaymentSnapshot,
    PaymentStatus,
    PaymentTransaction,
    PaymentTransactionType,
)
from app.observability.metrics import (
    OUTBOX_WRITTEN,
    PAYMENT_PROCESSING_DURATION,
    PAYMENTS_AUTHORIZED,
    PAYMENTS_CANCELLED,
    PAYMENTS_CAPTURED,
    PAYMENTS_CREATED,
    PAYMENTS_FAILED,
)


class PaymentOutboxService:
    def __init__(self, repository: PaymentOutboxRepository) -> None:
        self._repository = repository

    async def write(self, event: PaymentEvent) -> None:
        await self._repository.add(event)
        OUTBOX_WRITTEN.inc()


class PaymentService:
    def __init__(
        self,
        payments: PaymentRepository,
        transactions: PaymentTransactionRepository,
        orders: OrderService,
        gateway: PaymentGateway,
        outbox: PaymentOutboxService,
    ) -> None:
        self._payments = payments
        self._transactions = transactions
        self._orders = orders
        self._gateway = gateway
        self._outbox = outbox

    async def create(self, values: PaymentCreate) -> PaymentIntent:
        existing = await self._payments.get_by_idempotency(
            values.customer_id, values.idempotency_key
        )
        if existing is not None:
            if existing.order_id != values.order_id:
                raise _conflict("The Idempotency-Key belongs to another Payment.")
            return existing
        order = await self._orders.get_owned(values.order_id, values.customer_id)
        if order.status is not OrderStatus.PENDING:
            raise _conflict("Payments can be created only for pending Orders.")
        snapshot = PaymentSnapshot(
            order_id=order.id,
            customer_id=order.customer_id,
            store_id=order.store_id,
            money=Money(order.subtotal, order.currency),
        )
        payment_id = uuid7()
        with PAYMENT_PROCESSING_DURATION.time():
            result = await self._gateway.create_intent(
                payment_id=payment_id,
                amount=snapshot.money.amount,
                currency=snapshot.money.currency,
                idempotency_key=values.idempotency_key,
            )
        if result.status is not PaymentStatus.CREATED:
            raise _conflict("The Payment provider did not create an Intent.")
        now = datetime.now(UTC)
        payment = await self._payments.add(
            {
                "id": payment_id,
                "order_id": snapshot.order_id,
                "customer_id": snapshot.customer_id,
                "store_id": snapshot.store_id,
                "provider": values.provider,
                "provider_reference": result.provider_reference,
                "status": PaymentStatus.CREATED,
                "currency": snapshot.money.currency,
                "amount": snapshot.money.amount,
                "idempotency_key": values.idempotency_key,
                "expires_at": now + timedelta(minutes=15),
                "authorized_at": None,
                "captured_at": None,
                "failed_at": None,
                "cancelled_at": None,
                "created_by_id": values.customer_id,
                "updated_by_id": values.customer_id,
            }
        )
        await self._record(payment, result, PaymentTransactionType.CREATED, now)
        PAYMENTS_CREATED.inc()
        await self._emit(PaymentCreated, payment)
        return payment

    async def list_owned(
        self, customer_id: UUID, filters: PaymentFilter
    ) -> tuple[Sequence[PaymentIntent], int]:
        return await self._payments.list_for_customer(customer_id, filters)

    async def get_owned(self, payment_id: UUID, customer_id: UUID) -> PaymentIntent:
        payment = await self._payments.get_for_customer(payment_id, customer_id)
        if payment is None:
            raise _not_found()
        return payment

    async def get_for_refund(
        self, payment_id: UUID, customer_id: UUID
    ) -> PaymentIntent:
        payment = await self._payments.get_for_customer_locked(payment_id, customer_id)
        if payment is None:
            raise _not_found()
        return payment

    async def transactions_owned(
        self, payment_id: UUID, customer_id: UUID
    ) -> Sequence[PaymentTransaction]:
        payment = await self.get_owned(payment_id, customer_id)
        return await self._transactions.list_for_payment(payment.id)

    async def authorize_owned(
        self, payment_id: UUID, customer_id: UUID, values: PaymentTransition
    ) -> PaymentIntent:
        payment = await self.get_owned(payment_id, customer_id)
        if payment.status is not PaymentStatus.CREATED:
            raise _conflict("Only a created Payment can be authorized.")
        _validate_version(payment, values.expected_version)
        with PAYMENT_PROCESSING_DURATION.time():
            result = await self._gateway.authorize(
                payment_id=payment.id,
                provider_reference=payment.provider_reference,
            )
        return await self._apply_result(
            payment,
            values,
            result,
            expected={PaymentStatus.AUTHORIZED, PaymentStatus.FAILED},
        )

    async def capture_owned(
        self, payment_id: UUID, customer_id: UUID, values: PaymentTransition
    ) -> PaymentIntent:
        payment = await self.get_owned(payment_id, customer_id)
        if payment.status is not PaymentStatus.AUTHORIZED:
            raise _conflict("Only an authorized Payment can be captured.")
        _validate_version(payment, values.expected_version)
        with PAYMENT_PROCESSING_DURATION.time():
            result = await self._gateway.capture(
                payment_id=payment.id,
                provider_reference=payment.provider_reference,
            )
        transitioned = await self._apply_result(
            payment,
            values,
            result,
            expected={PaymentStatus.CAPTURED, PaymentStatus.FAILED},
        )
        if transitioned.status is PaymentStatus.CAPTURED:
            order = await self._orders.get_owned(payment.order_id, customer_id)
            await self._orders.confirm_owned(
                order.id,
                customer_id,
                OrderConfirm(expected_version=order.version, actor_id=values.actor_id),
            )
        return transitioned

    async def cancel_owned(
        self, payment_id: UUID, customer_id: UUID, values: PaymentTransition
    ) -> PaymentIntent:
        payment = await self.get_owned(payment_id, customer_id)
        if payment.status not in {PaymentStatus.CREATED, PaymentStatus.AUTHORIZED}:
            raise _conflict("Only a created or authorized Payment can be cancelled.")
        _validate_version(payment, values.expected_version)
        with PAYMENT_PROCESSING_DURATION.time():
            result = await self._gateway.cancel(
                payment_id=payment.id,
                provider_reference=payment.provider_reference,
            )
        return await self._apply_result(
            payment,
            values,
            result,
            expected={PaymentStatus.CANCELLED, PaymentStatus.FAILED},
        )

    async def status_owned(
        self, payment_id: UUID, customer_id: UUID
    ) -> PaymentGatewayResult:
        payment = await self.get_owned(payment_id, customer_id)
        with PAYMENT_PROCESSING_DURATION.time():
            return await self._gateway.status(
                payment_id=payment.id,
                provider_reference=payment.provider_reference,
                current_status=payment.status,
            )

    async def _apply_result(
        self,
        payment: PaymentIntent,
        values: PaymentTransition,
        result: PaymentGatewayResult,
        *,
        expected: set[PaymentStatus],
    ) -> PaymentIntent:
        if result.status not in expected:
            raise _conflict("The Payment provider returned an invalid transition.")
        now = datetime.now(UTC)
        transitioned = await self._payments.transition(
            payment.id,
            payment.customer_id,
            expected_version=values.expected_version,
            status=result.status,
            transitioned_at=now,
            actor_id=values.actor_id,
            archive=result.status is PaymentStatus.CANCELLED,
        )
        if transitioned is None:
            raise _conflict("The Payment was modified by another request.")
        event_type, transaction_type = _transition_contract(result.status)
        await self._record(transitioned, result, transaction_type, now)
        if result.status is PaymentStatus.AUTHORIZED:
            PAYMENTS_AUTHORIZED.inc()
        elif result.status is PaymentStatus.CAPTURED:
            PAYMENTS_CAPTURED.inc()
        elif result.status is PaymentStatus.FAILED:
            PAYMENTS_FAILED.inc()
        else:
            PAYMENTS_CANCELLED.inc()
        await self._emit(event_type, transitioned)
        return transitioned

    async def _record(
        self,
        payment: PaymentIntent,
        result: PaymentGatewayResult,
        event_type: PaymentTransactionType,
        occurred_at: datetime,
    ) -> None:
        await self._transactions.add(
            {
                "payment_intent_id": payment.id,
                "provider_transaction_id": result.provider_transaction_id,
                "event_type": event_type,
                "status": result.status,
                "amount": payment.amount,
                "currency": payment.currency,
                "provider_payload": result.payload,
                "occurred_at": occurred_at,
            }
        )

    async def _emit(
        self, event_type: type[PaymentEvent], payment: PaymentIntent
    ) -> None:
        await self._outbox.write(
            event_type(
                payment_id=payment.id,
                order_id=payment.order_id,
                customer_id=payment.customer_id,
                store_id=payment.store_id,
                version=payment.version,
            )
        )


def _transition_contract(
    status: PaymentStatus,
) -> tuple[type[PaymentEvent], PaymentTransactionType]:
    contracts: dict[
        PaymentStatus, tuple[type[PaymentEvent], PaymentTransactionType]
    ] = {
        PaymentStatus.AUTHORIZED: (
            PaymentAuthorized,
            PaymentTransactionType.AUTHORIZED,
        ),
        PaymentStatus.CAPTURED: (PaymentCaptured, PaymentTransactionType.CAPTURED),
        PaymentStatus.FAILED: (PaymentFailed, PaymentTransactionType.FAILED),
        PaymentStatus.CANCELLED: (PaymentCancelled, PaymentTransactionType.CANCELLED),
    }
    return contracts[status]


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Payment not found",
        detail="The requested Payment was not found.",
        status_code=404,
    )


def _validate_version(payment: PaymentIntent, expected_version: int) -> None:
    if payment.version != expected_version:
        raise _conflict("The Payment was modified by another request.")


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Payment conflict",
        detail=detail,
        status_code=409,
    )
