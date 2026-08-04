from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.modules.checkout.application.services import CheckoutService
from app.modules.checkout.domain import CheckoutStatus
from app.modules.inventory.application.services import InventoryService
from app.modules.inventory.domain import InventoryStatus
from app.modules.orders.application.services import OrderService
from app.modules.orders.domain import OrderItem, OrderStatus
from app.modules.payments.application.services import PaymentService
from app.modules.payments.domain import PaymentStatus
from app.modules.reservations.application.repositories import (
    ReservationItemRepository,
    ReservationOutboxRepository,
    ReservationRepository,
)
from app.modules.reservations.application.schemas import (
    ReservationCreate,
    ReservationFilter,
    ReservationTransition,
)
from app.modules.reservations.domain import (
    InventoryReservation,
    ReservationActivated,
    ReservationConsumed,
    ReservationCreated,
    ReservationEvent,
    ReservationExpired,
    ReservationItem,
    ReservationReleased,
    ReservationStatus,
)
from app.observability.metrics import (
    OUTBOX_WRITTEN,
    RESERVATION_DURATION,
    RESERVATIONS_CONSUMED,
    RESERVATIONS_CREATED,
    RESERVATIONS_EXPIRED,
    RESERVATIONS_RELEASED,
)


class ReservationOutboxService:
    def __init__(self, repository: ReservationOutboxRepository) -> None:
        self._repository = repository

    async def write(self, event: ReservationEvent) -> None:
        await self._repository.add(event)
        OUTBOX_WRITTEN.inc()


class ReservationService:
    def __init__(
        self,
        reservations: ReservationRepository,
        items: ReservationItemRepository,
        payments: PaymentService,
        orders: OrderService,
        checkouts: CheckoutService,
        inventory: InventoryService,
        outbox: ReservationOutboxService,
    ) -> None:
        self._reservations = reservations
        self._items = items
        self._payments = payments
        self._orders = orders
        self._checkouts = checkouts
        self._inventory = inventory
        self._outbox = outbox

    async def create(self, values: ReservationCreate) -> InventoryReservation:
        now = datetime.now(UTC)
        payment = await self._payments.get_owned(values.payment_id, values.actor_id)
        order = await self._orders.get_owned(values.order_id, values.actor_id)
        checkout = await self._checkouts.get_owned(
            order.checkout_session_id, values.actor_id
        )
        if payment.status is not PaymentStatus.CAPTURED:
            raise _conflict("Reservations require a captured Payment.")
        if order.status is not OrderStatus.CONFIRMED:
            raise _conflict("Reservations require a confirmed Order.")
        if checkout.status is not CheckoutStatus.CONFIRMED:
            raise _conflict("Reservations require a confirmed Checkout Session.")
        if (
            payment.order_id != order.id
            or payment.customer_id != order.customer_id
            or payment.store_id != order.store_id
            or checkout.user_id != order.customer_id
            or checkout.store_id != order.store_id
        ):
            raise _conflict("Payment, Order, and Checkout ownership do not match.")
        existing = await self._reservations.get_active_for_order(order.id)
        if existing is not None:
            if existing.expires_at <= now:
                await self._expire(existing, now)
            else:
                raise _conflict("This Order already has an active Reservation.")
        summary = await self._orders.summary_owned(order.id, values.actor_id)
        if not summary.items:
            raise _conflict("An Order without Items cannot be reserved.")
        expires_at = values.expires_at or now + timedelta(minutes=30)
        if expires_at.utcoffset() is None or expires_at <= now:
            raise _validation("expires_at", "Expiration must be a future timestamp.")
        prepared = [
            await self._prepare_item(item, order.store_id, now)
            for item in sorted(summary.items, key=lambda value: str(value.inventory_id))
        ]
        reservation = await self._reservations.add(
            {
                "order_id": order.id,
                "payment_id": payment.id,
                "customer_id": order.customer_id,
                "store_id": order.store_id,
                "status": ReservationStatus.CREATED,
                "expires_at": expires_at,
                "released_at": None,
                "consumed_at": None,
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        await self._items.add_many(
            [{**item, "reservation_id": reservation.id} for item in prepared]
        )
        RESERVATIONS_CREATED.inc()
        await self._emit(ReservationCreated, reservation)
        active = await self._reservations.transition(
            reservation.id,
            reservation.customer_id,
            expected_version=reservation.version,
            status=ReservationStatus.ACTIVE,
            transitioned_at=now,
            actor_id=values.actor_id,
        )
        if active is None:
            raise _conflict("The Reservation could not be activated.")
        await self._emit(ReservationActivated, active)
        return active

    async def list_owned(
        self, customer_id: UUID, filters: ReservationFilter
    ) -> tuple[Sequence[InventoryReservation], int]:
        values, total = await self._reservations.list_for_customer(customer_id, filters)
        return [await self._expire_if_needed(value) for value in values], total

    async def get_owned(
        self, reservation_id: UUID, customer_id: UUID
    ) -> InventoryReservation:
        reservation = await self._get_owned(reservation_id, customer_id)
        return await self._expire_if_needed(reservation)

    async def detail_owned(
        self, reservation_id: UUID, customer_id: UUID
    ) -> tuple[InventoryReservation, Sequence[ReservationItem]]:
        reservation = await self.get_owned(reservation_id, customer_id)
        items = await self._items.list_for_reservation(reservation.id)
        return reservation, items

    async def release_owned(
        self, reservation_id: UUID, customer_id: UUID, values: ReservationTransition
    ) -> InventoryReservation:
        reservation = await self.get_owned(reservation_id, customer_id)
        self._validate_active(reservation, values.expected_version)
        return await self._terminal_transition(
            reservation,
            values,
            status=ReservationStatus.RELEASED,
            event_type=ReservationReleased,
        )

    async def consume_owned(
        self, reservation_id: UUID, customer_id: UUID, values: ReservationTransition
    ) -> InventoryReservation:
        reservation = await self.get_owned(reservation_id, customer_id)
        self._validate_active(reservation, values.expected_version)
        return await self._terminal_transition(
            reservation,
            values,
            status=ReservationStatus.CONSUMED,
            event_type=ReservationConsumed,
        )

    async def _prepare_item(
        self, item: OrderItem, store_id: UUID, now: datetime
    ) -> Mapping[str, object]:
        inventory = await self._inventory.get_for_reservation(
            item.inventory_id, store_id
        )
        if inventory.status is not InventoryStatus.ACTIVE:
            raise _conflict("Inventory is not active.")
        if inventory.variant_id != item.variant_id:
            raise _conflict("Inventory does not match the ordered Variant.")
        if inventory.version != item.inventory_version:
            raise _conflict("Inventory changed after the Order snapshot.")
        active_quantity = await self._items.active_quantity(inventory.id, now)
        if inventory.quantity_available - active_quantity < item.quantity:
            raise _conflict("Insufficient available Inventory for the Reservation.")
        return {
            "inventory_item_id": inventory.id,
            "variant_id": inventory.variant_id,
            "quantity": item.quantity,
            "inventory_version": inventory.version,
        }

    async def _get_owned(
        self, reservation_id: UUID, customer_id: UUID
    ) -> InventoryReservation:
        reservation = await self._reservations.get_for_customer(
            reservation_id, customer_id
        )
        if reservation is None:
            raise _not_found()
        return reservation

    async def _expire_if_needed(
        self, reservation: InventoryReservation
    ) -> InventoryReservation:
        now = datetime.now(UTC)
        if (
            reservation.status is not ReservationStatus.ACTIVE
            or reservation.expires_at > now
        ):
            return reservation
        return await self._expire(reservation, now)

    async def _expire(
        self, reservation: InventoryReservation, now: datetime
    ) -> InventoryReservation:
        expired = await self._reservations.transition(
            reservation.id,
            reservation.customer_id,
            expected_version=reservation.version,
            status=ReservationStatus.EXPIRED,
            transitioned_at=now,
            actor_id=reservation.customer_id,
            archive=True,
        )
        if expired is None:
            raise _conflict("The Reservation was modified by another request.")
        RESERVATIONS_EXPIRED.inc()
        RESERVATION_DURATION.observe((now - reservation.created_at).total_seconds())
        await self._emit(ReservationExpired, expired)
        return expired

    async def _terminal_transition(
        self,
        reservation: InventoryReservation,
        values: ReservationTransition,
        *,
        status: ReservationStatus,
        event_type: type[ReservationEvent],
    ) -> InventoryReservation:
        now = datetime.now(UTC)
        transitioned = await self._reservations.transition(
            reservation.id,
            reservation.customer_id,
            expected_version=values.expected_version,
            status=status,
            transitioned_at=now,
            actor_id=values.actor_id,
            archive=status is ReservationStatus.RELEASED,
        )
        if transitioned is None:
            raise _conflict("The Reservation was modified by another request.")
        if status is ReservationStatus.RELEASED:
            RESERVATIONS_RELEASED.inc()
        else:
            RESERVATIONS_CONSUMED.inc()
        RESERVATION_DURATION.observe((now - reservation.created_at).total_seconds())
        await self._emit(event_type, transitioned)
        return transitioned

    @staticmethod
    def _validate_active(
        reservation: InventoryReservation, expected_version: int
    ) -> None:
        if reservation.status is not ReservationStatus.ACTIVE:
            raise _conflict("Only an active Reservation can be changed.")
        if reservation.version != expected_version:
            raise _conflict("The Reservation was modified by another request.")

    async def _emit(
        self, event_type: type[ReservationEvent], reservation: InventoryReservation
    ) -> None:
        await self._outbox.write(
            event_type(
                reservation_id=reservation.id,
                order_id=reservation.order_id,
                payment_id=reservation.payment_id,
                customer_id=reservation.customer_id,
                store_id=reservation.store_id,
                version=reservation.version,
            )
        )


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Reservation not found",
        detail="The requested Reservation was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Reservation conflict",
        detail=detail,
        status_code=409,
    )


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Reservation validation failed",
        detail="Reservation fields are invalid.",
        status_code=422,
        errors=[
            FieldError(field=field, code="invalid_reservation_field", message=message)
        ],
    )
