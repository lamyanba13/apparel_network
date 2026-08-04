from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.modules.inventory.application.services import InventoryService
from app.modules.orders.application.services import OrderService
from app.modules.orders.domain import OrderItem, OrderStatus
from app.modules.payments.application.services import PaymentService
from app.modules.payments.domain import PaymentIntent, PaymentStatus
from app.modules.returns.application.gateways import RefundGateway, RefundGatewayResult
from app.modules.returns.application.repositories import (
    RefundRepository,
    RefundTransactionRepository,
    ReturnItemRepository,
    ReturnOutboxRepository,
    ReturnRepository,
)
from app.modules.returns.application.schemas import (
    RefundCreate,
    RefundFilter,
    RefundTransition,
    ReturnCreate,
    ReturnFilter,
    ReturnInspection,
    ReturnTransition,
    ReturnUpdate,
)
from app.modules.returns.domain import (
    InventoryDisposition,
    ProductReturn,
    Refund,
    RefundCompleted,
    RefundCreated,
    RefundEvent,
    RefundFailed,
    RefundStatus,
    RefundTransaction,
    RefundTransactionType,
    ReturnApproved,
    ReturnCancelled,
    ReturnEvent,
    ReturnInspected,
    ReturnItem,
    ReturnReceived,
    ReturnRejected,
    ReturnRequested,
    ReturnStatus,
)
from app.modules.shipments.application.services import ShipmentService
from app.modules.shipments.domain import ShipmentStatus
from app.observability.metrics import (
    OUTBOX_WRITTEN,
    REFUND_DURATION,
    REFUNDS_COMPLETED,
    REFUNDS_FAILED,
    RETURNS_CREATED,
    RETURNS_RECEIVED,
    RETURNS_REFUNDED,
    RETURNS_REJECTED,
)


class ReturnOutboxService:
    def __init__(self, repository: ReturnOutboxRepository) -> None:
        self._repository = repository

    async def write(self, event: ReturnEvent | RefundEvent) -> None:
        await self._repository.add(event)
        OUTBOX_WRITTEN.inc()


class ReturnService:
    def __init__(
        self,
        returns: ReturnRepository,
        items: ReturnItemRepository,
        orders: OrderService,
        shipments: ShipmentService,
        payments: PaymentService,
        inventory: InventoryService,
        outbox: ReturnOutboxService,
    ) -> None:
        self._returns = returns
        self._items = items
        self._orders = orders
        self._shipments = shipments
        self._payments = payments
        self._inventory = inventory
        self._outbox = outbox

    async def create(self, values: ReturnCreate) -> ProductReturn:
        order = await self._orders.get_owned(values.order_id, values.actor_id)
        summary = await self._orders.summary_owned_for_return(
            values.order_id, values.actor_id
        )
        shipment = await self._shipments.get_owned(values.shipment_id, values.actor_id)
        payment = await self._payments.get_owned(values.payment_id, values.actor_id)
        if order.status is not OrderStatus.CONFIRMED:
            raise _conflict("Returns require an active confirmed Order.")
        if shipment.status is not ShipmentStatus.DELIVERED:
            raise _conflict("Returns require a delivered Shipment.")
        if payment.status is not PaymentStatus.CAPTURED:
            raise _conflict("Returns require a captured completed Payment.")
        if (
            shipment.order_id != order.id
            or shipment.payment_id != payment.id
            or payment.order_id != order.id
            or shipment.customer_id != order.customer_id
            or payment.customer_id != order.customer_id
            or shipment.store_id != order.store_id
            or payment.store_id != order.store_id
        ):
            raise _conflict("Order, Shipment, and Payment ownership do not match.")
        reason = _reason(values.reason)
        if not values.items:
            raise _validation("items", "At least one Return Item is required.")
        if len({item.order_item_id for item in values.items}) != len(values.items):
            raise _validation("items", "Order Items must be unique.")
        order_items = {item.id: item for item in summary.items}
        prepared: list[dict[str, object]] = []
        for requested in values.items:
            item = order_items.get(requested.order_item_id)
            if item is None:
                raise _conflict("A Return Item does not belong to the Order.")
            if requested.quantity <= 0:
                raise _validation("quantity", "Return quantity must be positive.")
            committed = await self._items.committed_quantity(item.id)
            if committed + requested.quantity > item.quantity:
                raise _conflict("Returned quantity exceeds purchased quantity.")
            inventory = await self._inventory.get_for_reservation(
                item.inventory_id, order.store_id
            )
            if inventory.variant_id != item.variant_id:
                raise _conflict("Return Inventory does not match the Order Item.")
            prepared.append(_item_values(item, requested.quantity))
        now = datetime.now(UTC)
        result = await self._returns.add(
            {
                "order_id": order.id,
                "shipment_id": shipment.id,
                "payment_id": payment.id,
                "customer_id": order.customer_id,
                "store_id": order.store_id,
                "status": ReturnStatus.REQUESTED,
                "reason": reason,
                "requested_at": now,
                "approved_at": None,
                "received_at": None,
                "inspected_at": None,
                "rejected_at": None,
                "cancelled_at": None,
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        await self._items.add_many(
            [{**item, "return_id": result.id} for item in prepared]
        )
        RETURNS_CREATED.inc()
        await self._emit(ReturnRequested, result)
        return result

    async def list_owned(
        self, customer_id: UUID, filters: ReturnFilter
    ) -> tuple[Sequence[ProductReturn], int]:
        return await self._returns.list_for_customer(customer_id, filters)

    async def get_owned(self, return_id: UUID, customer_id: UUID) -> ProductReturn:
        result = await self._returns.get_for_customer(return_id, customer_id)
        if result is None:
            raise _not_found("Return")
        return result

    async def detail_owned(
        self, return_id: UUID, customer_id: UUID
    ) -> tuple[ProductReturn, Sequence[ReturnItem]]:
        result = await self.get_owned(return_id, customer_id)
        return result, await self._items.list_for_return(result.id)

    async def update_owned(
        self, return_id: UUID, customer_id: UUID, values: ReturnUpdate
    ) -> ProductReturn:
        result = await self.get_owned(return_id, customer_id)
        self._validate(result, values.expected_version, {ReturnStatus.REQUESTED})
        updated = await self._returns.update_reason(
            result.id,
            customer_id,
            reason=_reason(values.reason),
            expected_version=values.expected_version,
            actor_id=values.actor_id,
        )
        if updated is None:
            raise _conflict("The Return was modified by another request.")
        return updated

    async def approve_owned(
        self, return_id: UUID, customer_id: UUID, values: ReturnTransition
    ) -> ProductReturn:
        return await self._transition_owned(
            return_id,
            customer_id,
            values,
            allowed={ReturnStatus.REQUESTED},
            status=ReturnStatus.APPROVED,
            event_type=ReturnApproved,
        )

    async def receive_owned(
        self, return_id: UUID, customer_id: UUID, values: ReturnTransition
    ) -> ProductReturn:
        result = await self._transition_owned(
            return_id,
            customer_id,
            values,
            allowed={ReturnStatus.APPROVED},
            status=ReturnStatus.RECEIVED,
            event_type=ReturnReceived,
        )
        RETURNS_RECEIVED.inc()
        return result

    async def inspect_owned(
        self, return_id: UUID, customer_id: UUID, values: ReturnInspection
    ) -> ProductReturn:
        result = await self.get_owned(return_id, customer_id)
        self._validate(result, values.expected_version, {ReturnStatus.RECEIVED})
        now = datetime.now(UTC)
        inspected_items = await self._items.inspect(result.id, values.dispositions, now)
        if not inspected_items:
            raise _validation(
                "dispositions", "Every Return Item requires a disposition."
            )
        inspected = await self._transition(
            result,
            values.expected_version,
            ReturnStatus.INSPECTED,
            values.actor_id,
            now,
        )
        await self._emit(ReturnInspected, inspected)
        return await self._transition(
            inspected,
            inspected.version,
            ReturnStatus.REFUND_PENDING,
            values.actor_id,
            now,
        )

    async def reject_owned(
        self, return_id: UUID, customer_id: UUID, values: ReturnTransition
    ) -> ProductReturn:
        result = await self._transition_owned(
            return_id,
            customer_id,
            values,
            allowed={ReturnStatus.REQUESTED},
            status=ReturnStatus.REJECTED,
            event_type=ReturnRejected,
            archive=True,
        )
        RETURNS_REJECTED.inc()
        return result

    async def cancel_owned(
        self, return_id: UUID, customer_id: UUID, values: ReturnTransition
    ) -> ProductReturn:
        return await self._transition_owned(
            return_id,
            customer_id,
            values,
            allowed={ReturnStatus.APPROVED},
            status=ReturnStatus.CANCELLED,
            event_type=ReturnCancelled,
            archive=True,
        )

    async def mark_refunded_owned(
        self, return_id: UUID, customer_id: UUID, actor_id: UUID
    ) -> ProductReturn:
        result = await self.get_owned(return_id, customer_id)
        if result.status is not ReturnStatus.REFUND_PENDING:
            raise _conflict("The Return is not awaiting a Refund.")
        transitioned = await self._transition(
            result,
            result.version,
            ReturnStatus.REFUNDED,
            actor_id,
            datetime.now(UTC),
        )
        RETURNS_REFUNDED.inc()
        return transitioned

    async def _transition_owned(
        self,
        return_id: UUID,
        customer_id: UUID,
        values: ReturnTransition,
        *,
        allowed: set[ReturnStatus],
        status: ReturnStatus,
        event_type: type[ReturnEvent],
        archive: bool = False,
    ) -> ProductReturn:
        result = await self.get_owned(return_id, customer_id)
        self._validate(result, values.expected_version, allowed)
        transitioned = await self._transition(
            result,
            values.expected_version,
            status,
            values.actor_id,
            datetime.now(UTC),
            archive=archive,
        )
        await self._emit(event_type, transitioned)
        return transitioned

    async def _transition(
        self,
        result: ProductReturn,
        expected_version: int,
        status: ReturnStatus,
        actor_id: UUID,
        now: datetime,
        *,
        archive: bool = False,
    ) -> ProductReturn:
        transitioned = await self._returns.transition(
            result.id,
            result.customer_id,
            expected_version=expected_version,
            status=status,
            transitioned_at=now,
            actor_id=actor_id,
            archive=archive,
        )
        if transitioned is None:
            raise _conflict("The Return was modified by another request.")
        return transitioned

    @staticmethod
    def _validate(
        result: ProductReturn, expected_version: int, allowed: set[ReturnStatus]
    ) -> None:
        if result.status not in allowed:
            raise _conflict("The Return cannot make this lifecycle transition.")
        if result.version != expected_version:
            raise _conflict("The Return was modified by another request.")

    async def _emit(self, event_type: type[ReturnEvent], result: ProductReturn) -> None:
        await self._outbox.write(
            event_type(
                return_id=result.id,
                order_id=result.order_id,
                customer_id=result.customer_id,
                store_id=result.store_id,
                version=result.version,
            )
        )


class RefundService:
    def __init__(
        self,
        refunds: RefundRepository,
        transactions: RefundTransactionRepository,
        returns: ReturnService,
        payments: PaymentService,
        gateway: RefundGateway,
        outbox: ReturnOutboxService,
    ) -> None:
        self._refunds = refunds
        self._transactions = transactions
        self._returns = returns
        self._payments = payments
        self._gateway = gateway
        self._outbox = outbox

    async def create(self, values: RefundCreate) -> Refund:
        result, items = await self._returns.detail_owned(
            values.return_id, values.actor_id
        )
        if result.status is not ReturnStatus.REFUND_PENDING:
            raise _conflict("Refunds require an inspected Return awaiting refund.")
        if await self._refunds.get_for_return(result.id) is not None:
            raise _conflict("This Return already has a Refund.")
        payment = await self._payments.get_for_refund(
            result.payment_id, values.actor_id
        )
        self._validate_payment(payment, result)
        amount = sum(
            (item.unit_price * item.quantity for item in items), start=Decimal()
        )
        completed = await self._refunds.completed_amount(payment.id)
        if amount <= 0 or completed + amount > payment.amount:
            raise _conflict("Refund amount exceeds the remaining captured Payment.")
        refund = await self._refunds.add(
            {
                "return_id": result.id,
                "payment_id": payment.id,
                "customer_id": result.customer_id,
                "store_id": result.store_id,
                "status": RefundStatus.PENDING,
                "amount": amount,
                "currency": payment.currency,
                "provider": "null",
                "provider_reference": None,
                "completed_at": None,
                "failed_at": None,
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        await self._transactions.add(
            {
                "refund_id": refund.id,
                "provider_transaction_id": f"local-created-{refund.id}",
                "event_type": RefundTransactionType.CREATED,
                "status": RefundStatus.PENDING,
                "provider_payload": {"gateway": "local", "operation": "created"},
                "occurred_at": datetime.now(UTC),
            }
        )
        await self._emit(RefundCreated, refund)
        return refund

    async def list_owned(
        self, customer_id: UUID, filters: RefundFilter
    ) -> tuple[Sequence[Refund], int]:
        return await self._refunds.list_for_customer(customer_id, filters)

    async def get_owned(self, refund_id: UUID, customer_id: UUID) -> Refund:
        refund = await self._refunds.get_for_customer(refund_id, customer_id)
        if refund is None:
            raise _not_found("Refund")
        return refund

    async def detail_owned(
        self, refund_id: UUID, customer_id: UUID
    ) -> tuple[Refund, Sequence[RefundTransaction]]:
        refund = await self.get_owned(refund_id, customer_id)
        return refund, await self._transactions.list_for_refund(refund.id)

    async def process_owned(
        self, refund_id: UUID, customer_id: UUID, values: RefundTransition
    ) -> Refund:
        refund = await self.get_owned(refund_id, customer_id)
        if refund.status is not RefundStatus.PENDING:
            raise _conflict("Only a pending Refund can be processed.")
        if refund.version != values.expected_version:
            raise _conflict("The Refund was modified by another request.")
        payment = await self._payments.get_owned(refund.payment_id, customer_id)
        result = await self._returns.get_owned(refund.return_id, customer_id)
        self._validate_payment(payment, result)
        gateway_result = await self._gateway.create_refund(
            refund_id=refund.id,
            payment_reference=payment.provider_reference,
            amount=refund.amount,
            currency=refund.currency,
        )
        refund = await self._apply(refund, values.actor_id, gateway_result)
        if refund.status is RefundStatus.FAILED:
            return refund
        gateway_result = await self._gateway.status(
            refund_id=refund.id,
            provider_reference=refund.provider_reference or "",
            current_status=refund.status,
        )
        refund = await self._apply(refund, values.actor_id, gateway_result)
        if refund.status is RefundStatus.COMPLETED:
            await self._returns.mark_refunded_owned(
                refund.return_id, customer_id, values.actor_id
            )
        return refund

    async def _apply(
        self, refund: Refund, actor_id: UUID, result: RefundGatewayResult
    ) -> Refund:
        if result.status not in {
            RefundStatus.PROCESSING,
            RefundStatus.COMPLETED,
            RefundStatus.FAILED,
        }:
            raise _conflict("The Refund provider returned an invalid transition.")
        now = datetime.now(UTC)
        transitioned = await self._refunds.transition(
            refund.id,
            refund.customer_id,
            expected_version=refund.version,
            status=result.status,
            provider_reference=result.provider_reference,
            transitioned_at=now,
            actor_id=actor_id,
        )
        if transitioned is None:
            raise _conflict("The Refund was modified by another request.")
        transaction_type = RefundTransactionType(result.status.value)
        await self._transactions.add(
            {
                "refund_id": transitioned.id,
                "provider_transaction_id": result.provider_transaction_id,
                "event_type": transaction_type,
                "status": result.status,
                "provider_payload": result.payload,
                "occurred_at": now,
            }
        )
        if result.status is RefundStatus.COMPLETED:
            REFUNDS_COMPLETED.inc()
            REFUND_DURATION.observe((now - refund.created_at).total_seconds())
            await self._emit(RefundCompleted, transitioned)
        elif result.status is RefundStatus.FAILED:
            REFUNDS_FAILED.inc()
            REFUND_DURATION.observe((now - refund.created_at).total_seconds())
            await self._emit(RefundFailed, transitioned)
        return transitioned

    @staticmethod
    def _validate_payment(payment: PaymentIntent, result: ProductReturn) -> None:
        if payment.status is not PaymentStatus.CAPTURED:
            raise _conflict("Refunds require a captured completed Payment.")
        if (
            payment.id != result.payment_id
            or payment.order_id != result.order_id
            or payment.customer_id != result.customer_id
            or payment.store_id != result.store_id
        ):
            raise _conflict("Refund Payment ownership does not match the Return.")

    async def _emit(self, event_type: type[RefundEvent], refund: Refund) -> None:
        await self._outbox.write(
            event_type(
                refund_id=refund.id,
                return_id=refund.return_id,
                payment_id=refund.payment_id,
                customer_id=refund.customer_id,
                store_id=refund.store_id,
                version=refund.version,
            )
        )


def _item_values(item: OrderItem, quantity: int) -> dict[str, object]:
    return {
        "order_item_id": item.id,
        "variant_id": item.variant_id,
        "inventory_item_id": item.inventory_id,
        "quantity": quantity,
        "unit_price": item.unit_price,
        "currency": item.currency,
        "disposition": InventoryDisposition.INSPECTION_REQUIRED,
        "inspected_at": None,
    }


def _reason(value: str) -> str:
    normalized = " ".join(value.split())
    if not 1 <= len(normalized) <= 1000:
        raise _validation("reason", "Return reason is invalid.")
    return normalized


def _not_found(resource: str) -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title=f"{resource} not found",
        detail=f"The requested {resource} was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Return or Refund conflict",
        detail=detail,
        status_code=409,
    )


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Return validation failed",
        detail="Return fields are invalid.",
        status_code=422,
        errors=[FieldError(field=field, code="invalid_return_field", message=message)],
    )
