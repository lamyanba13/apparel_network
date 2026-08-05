from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.common.errors import ErrorCode
from app.common.exceptions import AppError
from app.modules.checkout.application.services import CheckoutService
from app.modules.checkout.domain import CheckoutItem, CheckoutSession, CheckoutStatus
from app.modules.orders.application.repositories import (
    OrderItemRepository,
    OrderOutboxRepository,
    OrderRepository,
)
from app.modules.orders.application.schemas import (
    OrderConfirm,
    OrderCreate,
    OrderFilter,
    OrderSummary,
)
from app.modules.orders.domain import (
    Money,
    Order,
    OrderCancelled,
    OrderConfirmed,
    OrderCreated,
    OrderEvent,
    OrderNumber,
    OrderSnapshot,
    OrderStatus,
)
from app.observability.metrics import (
    ORDERS_CANCELLED,
    ORDERS_CONFIRMED,
    ORDERS_CREATED,
    OUTBOX_WRITTEN,
)


class OrderNumberService:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    async def next(self, *, now: datetime) -> OrderNumber:
        return OrderNumber.create(
            now.date(), await self._repository.next_number_value()
        )


class OrderValidationService:
    @staticmethod
    def checkout(value: CheckoutSession) -> None:
        if value.status is not CheckoutStatus.CONFIRMED:
            raise _conflict("Only a confirmed Checkout Session can create an Order.")

    @staticmethod
    def items(values: Sequence[CheckoutItem]) -> None:
        if not values:
            raise _conflict("A Checkout Session without Items cannot create an Order.")

    @staticmethod
    def confirmable(value: Order) -> None:
        if value.status is not OrderStatus.PENDING:
            raise _conflict("Only a pending Order can be confirmed.")

    @staticmethod
    def cancellable(value: Order) -> None:
        if value.status is not OrderStatus.CONFIRMED:
            raise _conflict("Only a confirmed Order can be cancelled.")


class OrderOutboxService:
    def __init__(self, repository: OrderOutboxRepository) -> None:
        self._repository = repository

    async def write(self, event: OrderEvent) -> None:
        await self._repository.add(event)
        OUTBOX_WRITTEN.inc()


class OrderService:
    def __init__(
        self,
        orders: OrderRepository,
        items: OrderItemRepository,
        checkouts: CheckoutService,
        numbers: OrderNumberService,
        outbox: OrderOutboxService,
    ) -> None:
        self._orders = orders
        self._items = items
        self._checkouts = checkouts
        self._numbers = numbers
        self._outbox = outbox
        self._validation = OrderValidationService()

    async def create(self, values: OrderCreate) -> Order:
        checkout = await self._checkouts.get_owned(
            values.checkout_session_id, values.actor_id
        )
        self._validation.checkout(checkout)
        if await self._orders.exists_for_checkout(checkout.id):
            raise _conflict("This Checkout Session already has an Order.")
        checkout_summary = await self._checkouts.summary_owned(
            checkout.id, values.actor_id
        )
        self._validation.items(checkout_summary.items)
        now = datetime.now(UTC)
        order_number = await self._numbers.next(now=now)
        order = await self._orders.add(
            {
                "checkout_session_id": checkout.id,
                "cart_id": checkout.cart_id,
                "store_id": checkout.store_id,
                "customer_id": checkout.user_id,
                "order_number": order_number.value,
                "status": OrderStatus.PENDING,
                "currency": checkout.currency,
                "subtotal": checkout.subtotal,
                "placed_at": now,
                "confirmed_at": None,
                "cancelled_at": None,
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        await self._items.add_many(
            [
                self._item_values(order.id, values.actor_id, item)
                for item in checkout_summary.items
            ]
        )
        await self._checkouts.inherit_promotions_to_order(
            checkout.id, order.id, values.actor_id
        )
        ORDERS_CREATED.inc()
        await self._emit(OrderCreated, order)
        return order

    async def list_owned(
        self, customer_id: UUID, filters: OrderFilter
    ) -> tuple[Sequence[Order], int]:
        return await self._orders.list_for_customer(customer_id, filters)

    async def get_owned(self, order_id: UUID, customer_id: UUID) -> Order:
        order = await self._orders.get_for_customer(order_id, customer_id)
        if order is None:
            raise _not_found()
        return order

    async def confirm_owned(
        self,
        order_id: UUID,
        customer_id: UUID,
        values: OrderConfirm,
    ) -> Order:
        order = await self.get_owned(order_id, customer_id)
        self._validation.confirmable(order)
        confirmed = await self._orders.transition(
            order.id,
            customer_id,
            expected_version=values.expected_version,
            status=OrderStatus.CONFIRMED,
            transitioned_at=datetime.now(UTC),
            actor_id=values.actor_id,
        )
        if confirmed is None:
            raise _conflict("The Order was modified by another request.")
        ORDERS_CONFIRMED.inc()
        await self._emit(OrderConfirmed, confirmed)
        return confirmed

    async def cancel_owned(
        self, order_id: UUID, customer_id: UUID, expected_version: int
    ) -> None:
        order = await self.get_owned(order_id, customer_id)
        self._validation.cancellable(order)
        now = datetime.now(UTC)
        cancelled = await self._orders.archive(
            order.id,
            customer_id,
            expected_version=expected_version,
            deleted_at=now,
            deleted_by_id=customer_id,
        )
        if cancelled is None:
            raise _conflict("The Order was modified by another request.")
        ORDERS_CANCELLED.inc()
        await self._emit(OrderCancelled, cancelled)

    async def summary_owned(self, order_id: UUID, customer_id: UUID) -> OrderSummary:
        order = await self.get_owned(order_id, customer_id)
        items = await self._items.list_for_order(order.id)
        promotions = await self._checkouts.order_promotion_snapshots_owned(
            order.id, customer_id
        )
        discount_total = sum(
            (promotion.discount_amount for promotion in promotions), start=Decimal("0")
        )
        return OrderSummary(
            order_id=order.id,
            items=items,
            subtotal=order.subtotal,
            discount_total=discount_total,
            final_total=order.subtotal - discount_total,
            currency=order.currency,
            quantity=sum(item.quantity for item in items),
            applied_promotions=promotions,
        )

    async def summary_owned_for_return(
        self, order_id: UUID, customer_id: UUID
    ) -> OrderSummary:
        order = await self.get_owned(order_id, customer_id)
        items = await self._items.list_for_order_locked(order.id)
        promotions = await self._checkouts.order_promotion_snapshots_owned(
            order.id, customer_id
        )
        discount_total = sum(
            (promotion.discount_amount for promotion in promotions), start=Decimal("0")
        )
        return OrderSummary(
            order_id=order.id,
            items=items,
            subtotal=order.subtotal,
            discount_total=discount_total,
            final_total=order.subtotal - discount_total,
            currency=order.currency,
            quantity=sum(item.quantity for item in items),
            applied_promotions=promotions,
        )

    @staticmethod
    def _item_values(
        order_id: UUID, actor_id: UUID, item: CheckoutItem
    ) -> Mapping[str, object]:
        snapshot = OrderSnapshot(
            price_id=item.price_id,
            money=Money(item.unit_price, item.currency),
            inventory_id=item.inventory_id,
            inventory_version=item.inventory_version,
            snapshot_timestamp=max(
                item.price_snapshot_time, item.inventory_snapshot_time
            ),
        )
        return {
            "order_id": order_id,
            "product_id": item.product_id,
            "variant_id": item.variant_id,
            "quantity": item.quantity,
            "price_id": snapshot.price_id,
            "unit_price": snapshot.money.amount,
            "currency": snapshot.money.currency,
            "inventory_id": snapshot.inventory_id,
            "inventory_version": snapshot.inventory_version,
            "snapshot_timestamp": snapshot.snapshot_timestamp,
            "created_by_id": actor_id,
            "updated_by_id": actor_id,
        }

    async def _emit(self, event_type: type[OrderEvent], order: Order) -> None:
        await self._outbox.write(
            event_type(
                order_id=order.id,
                checkout_session_id=order.checkout_session_id,
                customer_id=order.customer_id,
                store_id=order.store_id,
                version=order.version,
            )
        )


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Order not found",
        detail="The requested Order was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Order conflict",
        detail=detail,
        status_code=409,
    )
