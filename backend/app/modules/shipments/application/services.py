from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.modules.inventory.application.schemas import InventoryReservationConsumption
from app.modules.inventory.application.services import InventoryService
from app.modules.orders.application.services import OrderService
from app.modules.orders.domain import OrderStatus
from app.modules.payments.application.services import PaymentService
from app.modules.payments.domain import PaymentStatus
from app.modules.reservations.application.services import ReservationService
from app.modules.reservations.domain import ReservationStatus
from app.modules.shipments.application.gateways import ShippingGateway
from app.modules.shipments.application.repositories import (
    ShipmentOutboxRepository,
    ShipmentPackageRepository,
    ShipmentRepository,
    ShipmentTrackingRepository,
)
from app.modules.shipments.application.schemas import (
    ShipmentCreate,
    ShipmentFilter,
    ShipmentPack,
    ShipmentTransition,
)
from app.modules.shipments.domain import (
    Shipment,
    ShipmentCancelled,
    ShipmentCreated,
    ShipmentDelivered,
    ShipmentEvent,
    ShipmentOutForDelivery,
    ShipmentPackage,
    ShipmentPacked,
    ShipmentReturned,
    ShipmentReturnRequested,
    ShipmentShipped,
    ShipmentStatus,
    ShipmentTrackingEvent,
)
from app.observability.metrics import (
    DELIVERY_DURATION,
    OUTBOX_WRITTEN,
    SHIPMENTS_CANCELLED,
    SHIPMENTS_CREATED,
    SHIPMENTS_DELIVERED,
    SHIPMENTS_PACKED,
    SHIPMENTS_SHIPPED,
)


class ShipmentOutboxService:
    def __init__(self, repository: ShipmentOutboxRepository) -> None:
        self._repository = repository

    async def write(self, event: ShipmentEvent) -> None:
        await self._repository.add(event)
        OUTBOX_WRITTEN.inc()


class ShipmentService:
    def __init__(
        self,
        shipments: ShipmentRepository,
        packages: ShipmentPackageRepository,
        tracking: ShipmentTrackingRepository,
        payments: PaymentService,
        orders: OrderService,
        reservations: ReservationService,
        inventory: InventoryService,
        gateway: ShippingGateway,
        outbox: ShipmentOutboxService,
    ) -> None:
        self._shipments = shipments
        self._packages = packages
        self._tracking = tracking
        self._payments = payments
        self._orders = orders
        self._reservations = reservations
        self._inventory = inventory
        self._gateway = gateway
        self._outbox = outbox

    async def create(self, values: ShipmentCreate) -> Shipment:
        now = datetime.now(UTC)
        payment = await self._payments.get_owned(values.payment_id, values.actor_id)
        order = await self._orders.get_owned(values.order_id, values.actor_id)
        reservation, _ = await self._reservations.detail_owned(
            values.reservation_id, values.actor_id
        )
        if payment.status is not PaymentStatus.CAPTURED:
            raise _conflict("Shipments require a captured Payment.")
        if order.status is not OrderStatus.CONFIRMED:
            raise _conflict("Shipments require a confirmed Order.")
        if reservation.status is not ReservationStatus.CONSUMED:
            raise _conflict("Shipments require a consumed Reservation.")
        if (
            payment.id != reservation.payment_id
            or payment.order_id != order.id
            or reservation.order_id != order.id
            or payment.customer_id != order.customer_id
            or reservation.customer_id != order.customer_id
            or payment.store_id != order.store_id
            or reservation.store_id != order.store_id
        ):
            raise _conflict("Payment, Order, and Reservation ownership do not match.")
        if await self._shipments.get_for_order(order.id) is not None:
            raise _conflict("This Order already has a Shipment.")
        shipping_method = values.shipping_method.strip().lower()
        if not shipping_method or len(shipping_method) > 100:
            raise _validation("shipping_method", "Shipping method is invalid.")
        estimated_delivery = await self._gateway.estimate(
            shipping_method=shipping_method, requested_at=now
        )
        shipment = await self._shipments.add(
            {
                "order_id": order.id,
                "reservation_id": reservation.id,
                "payment_id": payment.id,
                "customer_id": order.customer_id,
                "store_id": order.store_id,
                "status": ShipmentStatus.CREATED,
                "carrier": None,
                "tracking_number": None,
                "tracking_url": None,
                "shipping_method": shipping_method,
                "estimated_delivery_at": estimated_delivery,
                "shipped_at": None,
                "delivered_at": None,
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        await self._record(shipment, "Shipment created.", now)
        SHIPMENTS_CREATED.inc()
        await self._emit(ShipmentCreated, shipment)
        ready = await self._transition(
            shipment,
            shipment.version,
            ShipmentStatus.READY_FOR_FULFILLMENT,
            values.actor_id,
            now,
        )
        await self._record(ready, "Ready for fulfillment.", now)
        return ready

    async def list_owned(
        self, customer_id: UUID, filters: ShipmentFilter
    ) -> tuple[Sequence[Shipment], int]:
        return await self._shipments.list_for_customer(customer_id, filters)

    async def get_owned(self, shipment_id: UUID, customer_id: UUID) -> Shipment:
        shipment = await self._shipments.get_for_customer(shipment_id, customer_id)
        if shipment is None:
            raise _not_found()
        return shipment

    async def detail_owned(
        self, shipment_id: UUID, customer_id: UUID
    ) -> tuple[Shipment, Sequence[ShipmentPackage], Sequence[ShipmentTrackingEvent]]:
        shipment = await self.get_owned(shipment_id, customer_id)
        return (
            shipment,
            await self._packages.list_for_shipment(shipment.id),
            await self._tracking.list_for_shipment(shipment.id),
        )

    async def tracking_owned(
        self, shipment_id: UUID, customer_id: UUID
    ) -> Sequence[ShipmentTrackingEvent]:
        shipment = await self.get_owned(shipment_id, customer_id)
        if shipment.tracking_number is not None:
            await self._gateway.track(
                shipment_id=shipment.id, tracking_number=shipment.tracking_number
            )
        return await self._tracking.list_for_shipment(shipment.id)

    async def pack_owned(
        self, shipment_id: UUID, customer_id: UUID, values: ShipmentPack
    ) -> Shipment:
        shipment = await self.get_owned(shipment_id, customer_id)
        self._validate_transition(
            shipment, values.expected_version, {ShipmentStatus.READY_FOR_FULFILLMENT}
        )
        if not values.packages:
            raise _validation("packages", "At least one package is required.")
        if len({item.package_number for item in values.packages}) != len(
            values.packages
        ):
            raise _validation("packages", "Package numbers must be unique.")
        labels = []
        package_values = []
        for package in values.packages:
            if any(
                dimension <= 0
                for dimension in (
                    package.weight,
                    package.length,
                    package.width,
                    package.height,
                )
            ):
                raise _validation("packages", "Package measurements must be positive.")
            label = await self._gateway.create_label(
                shipment_id=shipment.id, package=package
            )
            labels.append(label)
            package_values.append(
                {
                    "shipment_id": shipment.id,
                    "package_number": package.package_number,
                    "weight": package.weight,
                    "length": package.length,
                    "width": package.width,
                    "height": package.height,
                    "label_url": label.label_url,
                }
            )
        await self._packages.add_many(package_values)
        now = datetime.now(UTC)
        packed = await self._transition(
            shipment,
            values.expected_version,
            ShipmentStatus.PACKED,
            values.actor_id,
            now,
            values={
                "carrier": labels[0].carrier,
                "tracking_number": labels[0].tracking_number,
                "tracking_url": labels[0].tracking_url,
            },
        )
        await self._record(packed, "Shipment packed.", now)
        SHIPMENTS_PACKED.inc()
        await self._emit(ShipmentPacked, packed)
        return packed

    async def ship_owned(
        self, shipment_id: UUID, customer_id: UUID, values: ShipmentTransition
    ) -> Shipment:
        shipment = await self.get_owned(shipment_id, customer_id)
        self._validate_transition(
            shipment, values.expected_version, {ShipmentStatus.PACKED}
        )
        reservation, items = await self._reservations.detail_owned(
            shipment.reservation_id, customer_id
        )
        if reservation.status is not ReservationStatus.CONSUMED:
            raise _conflict("The Shipment Reservation is not consumed.")
        await self._inventory.consume_reservation(
            shipment.store_id,
            tuple(
                InventoryReservationConsumption(item.inventory_item_id, item.quantity)
                for item in items
            ),
            values.actor_id,
        )
        await self._gateway.manifest(shipment_id=shipment.id)
        now = datetime.now(UTC)
        shipped = await self._transition(
            shipment,
            values.expected_version,
            ShipmentStatus.SHIPPED,
            values.actor_id,
            now,
        )
        await self._record(shipped, "Shipment dispatched.", now)
        SHIPMENTS_SHIPPED.inc()
        await self._emit(ShipmentShipped, shipped)
        return shipped

    async def deliver_owned(
        self, shipment_id: UUID, customer_id: UUID, values: ShipmentTransition
    ) -> Shipment:
        shipment = await self.get_owned(shipment_id, customer_id)
        self._validate_transition(
            shipment,
            values.expected_version,
            {ShipmentStatus.SHIPPED, ShipmentStatus.OUT_FOR_DELIVERY},
        )
        now = datetime.now(UTC)
        if shipment.status is ShipmentStatus.SHIPPED:
            shipment = await self._transition(
                shipment,
                values.expected_version,
                ShipmentStatus.OUT_FOR_DELIVERY,
                values.actor_id,
                now,
            )
            await self._record(shipment, "Out for delivery.", now)
            await self._emit(ShipmentOutForDelivery, shipment)
        delivered = await self._transition(
            shipment,
            shipment.version,
            ShipmentStatus.DELIVERED,
            values.actor_id,
            now,
        )
        await self._record(delivered, "Shipment delivered.", now)
        SHIPMENTS_DELIVERED.inc()
        if delivered.shipped_at is not None:
            DELIVERY_DURATION.observe((now - delivered.shipped_at).total_seconds())
        await self._emit(ShipmentDelivered, delivered)
        return delivered

    async def cancel_owned(
        self, shipment_id: UUID, customer_id: UUID, values: ShipmentTransition
    ) -> Shipment:
        shipment = await self.get_owned(shipment_id, customer_id)
        self._validate_transition(
            shipment, values.expected_version, {ShipmentStatus.PACKED}
        )
        await self._gateway.cancel_label(
            shipment_id=shipment.id, tracking_number=shipment.tracking_number
        )
        now = datetime.now(UTC)
        cancelled = await self._transition(
            shipment,
            values.expected_version,
            ShipmentStatus.CANCELLED,
            values.actor_id,
            now,
            archive=True,
        )
        await self._record(cancelled, "Shipment cancelled.", now)
        SHIPMENTS_CANCELLED.inc()
        await self._emit(ShipmentCancelled, cancelled)
        return cancelled

    async def request_return_owned(
        self, shipment_id: UUID, customer_id: UUID, values: ShipmentTransition
    ) -> Shipment:
        shipment = await self.get_owned(shipment_id, customer_id)
        self._validate_transition(
            shipment, values.expected_version, {ShipmentStatus.SHIPPED}
        )
        now = datetime.now(UTC)
        result = await self._transition(
            shipment,
            values.expected_version,
            ShipmentStatus.RETURN_REQUESTED,
            values.actor_id,
            now,
        )
        await self._record(result, "Shipment return requested.", now)
        await self._emit(ShipmentReturnRequested, result)
        return result

    async def return_owned(
        self, shipment_id: UUID, customer_id: UUID, values: ShipmentTransition
    ) -> Shipment:
        shipment = await self.get_owned(shipment_id, customer_id)
        self._validate_transition(
            shipment, values.expected_version, {ShipmentStatus.RETURN_REQUESTED}
        )
        now = datetime.now(UTC)
        result = await self._transition(
            shipment,
            values.expected_version,
            ShipmentStatus.RETURNED,
            values.actor_id,
            now,
        )
        await self._record(result, "Shipment returned.", now)
        await self._emit(ShipmentReturned, result)
        return result

    async def _transition(
        self,
        shipment: Shipment,
        expected_version: int,
        status: ShipmentStatus,
        actor_id: UUID,
        now: datetime,
        *,
        values: dict[str, object] | None = None,
        archive: bool = False,
    ) -> Shipment:
        transitioned = await self._shipments.transition(
            shipment.id,
            shipment.customer_id,
            expected_version=expected_version,
            status=status,
            actor_id=actor_id,
            transitioned_at=now,
            values=values,
            archive=archive,
        )
        if transitioned is None:
            raise _conflict("The Shipment was modified by another request.")
        return transitioned

    async def _record(
        self, shipment: Shipment, description: str, occurred_at: datetime
    ) -> None:
        await self._tracking.add(shipment.id, shipment.status, description, occurred_at)

    async def _emit(self, event_type: type[ShipmentEvent], shipment: Shipment) -> None:
        await self._outbox.write(
            event_type(
                shipment_id=shipment.id,
                order_id=shipment.order_id,
                reservation_id=shipment.reservation_id,
                payment_id=shipment.payment_id,
                customer_id=shipment.customer_id,
                store_id=shipment.store_id,
                version=shipment.version,
            )
        )

    @staticmethod
    def _validate_transition(
        shipment: Shipment,
        expected_version: int,
        allowed: set[ShipmentStatus],
    ) -> None:
        if shipment.status not in allowed:
            raise _conflict("The Shipment cannot make this lifecycle transition.")
        if shipment.version != expected_version:
            raise _conflict("The Shipment was modified by another request.")


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Shipment not found",
        detail="The requested Shipment was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Shipment conflict",
        detail=detail,
        status_code=409,
    )


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Shipment validation failed",
        detail="Shipment fields are invalid.",
        status_code=422,
        errors=[
            FieldError(field=field, code="invalid_shipment_field", message=message)
        ],
    )
