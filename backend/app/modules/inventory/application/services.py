from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.inventory.application.repositories import (
    InventoryMovementRepository,
    InventoryRepository,
    RetailerOperationsRepository,
)
from app.modules.inventory.application.schemas import (
    InventoryAdjustment,
    InventoryCreate,
    InventoryMovementFilter,
    InventoryReconciliation,
    InventoryReservationConsumption,
    InventoryStockFilter,
    InventoryUpdate,
    RetailerActivityFilter,
)
from app.modules.inventory.domain import (
    InventoryAdjusted,
    InventoryCreated,
    InventoryDeleted,
    InventoryItem,
    InventoryLowStock,
    InventoryMovement,
    InventoryMovementType,
    InventoryOutOfStock,
    InventoryReconciled,
    InventoryStatus,
    InventoryStock,
    InventoryUpdated,
    RetailerOperationsSummary,
    RetailerOrderActivity,
    RetailerShipmentActivity,
    TrackingPolicy,
)
from app.observability.metrics import (
    INVENTORY_ADJUSTMENT_DURATION,
    INVENTORY_ADJUSTMENTS,
    INVENTORY_CREATED,
    INVENTORY_DELETED,
    INVENTORY_LOW_STOCK,
    INVENTORY_OUT_OF_STOCK,
    INVENTORY_RECONCILED,
    INVENTORY_UPDATED,
)


class InventoryValidationService:
    def create(self, values: InventoryCreate) -> dict[str, object]:
        result = asdict(values)
        self.quantities(result)
        self.status(values.status)
        self.tracking(values.tracking_policy)
        self.threshold(values.low_stock_threshold)
        return result

    def changes(self, values: Mapping[str, object]) -> dict[str, object]:
        allowed = {
            "quantity_on_hand",
            "quantity_reserved",
            "status",
            "tracking_policy",
            "low_stock_threshold",
        }
        if not values or not set(values) <= allowed:
            raise _validation("body", "At least one supported field is required.")
        result = dict(values)
        if "status" in result:
            self.status(result["status"])
        if "tracking_policy" in result:
            self.tracking(result["tracking_policy"])
        if "low_stock_threshold" in result:
            self.threshold(result["low_stock_threshold"])
        for field in ("quantity_on_hand", "quantity_reserved"):
            value = result.get(field)
            if value is not None and (not isinstance(value, int) or value < 0):
                raise _validation(field, "Quantity must be non-negative.")
        return result

    @staticmethod
    def quantities(values: Mapping[str, object]) -> None:
        on_hand, reserved = values["quantity_on_hand"], values["quantity_reserved"]
        if not isinstance(on_hand, int) or on_hand < 0:
            raise _validation("quantity_on_hand", "Quantity must be non-negative.")
        if (
            not isinstance(reserved, int)
            or reserved < 0
            or not isinstance(on_hand, int)
            or reserved > on_hand
        ):
            raise _validation("quantity_reserved", "Reserved quantity is invalid.")

    @staticmethod
    def status(value: object) -> None:
        if not isinstance(value, InventoryStatus):
            raise _validation("status", "Inventory status is invalid.")

    @staticmethod
    def tracking(value: object) -> None:
        if not isinstance(value, TrackingPolicy):
            raise _validation("tracking_policy", "Tracking policy is invalid.")

    @staticmethod
    def threshold(value: object) -> None:
        if not isinstance(value, int) or value < 0:
            raise _validation("low_stock_threshold", "Threshold must be non-negative.")


class InventoryService:
    def __init__(
        self,
        repository: InventoryRepository,
        events: EventPublisher,
        movements: InventoryMovementRepository | None = None,
    ) -> None:
        self._repository, self._events = repository, events
        self._movements = movements
        self._validation = InventoryValidationService()

    async def create(self, values: InventoryCreate) -> InventoryItem:
        context = await self._repository.variant_context(
            values.variant_id, values.actor_id
        )
        if context is None:
            raise _not_found()
        if await self._repository.variant_has_inventory(values.variant_id):
            raise _conflict("This variant already has inventory.")
        validated = self._validation.create(values)
        item = await self._repository.add(
            {
                **validated,
                **context,
                "quantity_available": values.quantity_on_hand
                - values.quantity_reserved,
                "sku_snapshot": context["reference"],
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        await self._record_movement(
            item,
            movement_type=InventoryMovementType.INITIAL_STOCK,
            quantity_delta=item.quantity_on_hand,
            previous_on_hand=0,
            previous_available=0,
            reservation_quantity=item.quantity_reserved,
            reason="Initial stock setup",
            actor_id=values.actor_id,
            source="inventory_create",
            reference_id=None,
        )
        INVENTORY_CREATED.inc()
        await self._publish(InventoryCreated, item)
        return item

    async def list_owned(
        self, owner_id: UUID, **filters: object
    ) -> tuple[Sequence[InventoryItem], int]:
        return await self._repository.list_for_owner(owner_id, **filters)

    async def get_owned(self, inventory_id: UUID, owner_id: UUID) -> InventoryItem:
        item = await self._repository.get_for_owner(inventory_id, owner_id)
        if item is None:
            raise _not_found()
        return item

    async def get_for_reservation(
        self, inventory_id: UUID, store_id: UUID
    ) -> InventoryItem:
        item = await self._repository.get_for_store(inventory_id, store_id)
        if item is None:
            raise _not_found()
        return item

    async def consume_reservation(
        self,
        store_id: UUID,
        values: Sequence[InventoryReservationConsumption],
        actor_id: UUID,
    ) -> Sequence[InventoryItem]:
        consumed: list[InventoryItem] = []
        for value in sorted(values, key=lambda item: str(item.inventory_id)):
            if value.quantity <= 0:
                raise _validation("quantity", "Quantity must be positive.")
            existing = await self.get_for_reservation(value.inventory_id, store_id)
            if existing.status is not InventoryStatus.ACTIVE:
                raise _conflict("Inventory is not active.")
            item = await self._repository.consume(
                value.inventory_id,
                store_id,
                quantity=value.quantity,
                actor_id=actor_id,
                expected_version=existing.version,
            )
            if item is None:
                raise _conflict("Inventory could not be consumed for the Shipment.")
            await self._record_movement(
                item,
                movement_type=InventoryMovementType.RESERVATION_CONSUMPTION,
                quantity_delta=-value.quantity,
                previous_on_hand=existing.quantity_on_hand,
                previous_available=existing.quantity_available,
                reservation_quantity=value.quantity,
                reason="Consumed by Shipment dispatch",
                actor_id=actor_id,
                source="shipment",
                reference_id=None,
            )
            INVENTORY_UPDATED.inc()
            INVENTORY_ADJUSTMENTS.inc()
            await self._publish(InventoryUpdated, item)
            await self._publish(InventoryAdjusted, item)
            consumed.append(item)
        return consumed

    async def update_owned(
        self, inventory_id: UUID, owner_id: UUID, values: InventoryUpdate
    ) -> InventoryItem:
        existing = await self._repository.get_locked_for_operator(
            inventory_id, owner_id
        )
        if existing is None:
            raise _not_found()
        if existing.version != values.expected_version:
            raise _conflict("The inventory item was modified by another request.")
        changes = self._validation.changes(values.values)
        on_hand_value = changes.get("quantity_on_hand", existing.quantity_on_hand)
        reserved_value = changes.get("quantity_reserved", existing.quantity_reserved)
        if not isinstance(on_hand_value, int) or not isinstance(reserved_value, int):
            raise _validation("quantity", "Quantity must be non-negative.")
        on_hand, reserved = on_hand_value, reserved_value
        self._validation.quantities(
            {"quantity_on_hand": on_hand, "quantity_reserved": reserved}
        )
        active_reservations = 0
        quantity_changed = (
            on_hand != existing.quantity_on_hand
            or reserved != existing.quantity_reserved
        )
        if quantity_changed:
            active_reservations = await self._repository.active_reservation_quantity(
                inventory_id, datetime.now(UTC)
            )
            if on_hand - reserved < active_reservations:
                raise _conflict(
                    "The quantity would invalidate active Inventory Reservations."
                )
        changes["quantity_available"] = on_hand - reserved
        item = await self._repository.update(
            inventory_id,
            owner_id,
            values={**changes, "updated_by_id": values.actor_id},
            expected_version=values.expected_version,
        )
        if item is None:
            raise _conflict("The inventory item was modified by another request.")
        INVENTORY_UPDATED.inc()
        await self._publish(InventoryUpdated, item)
        if quantity_changed:
            await self._record_movement(
                item,
                movement_type=InventoryMovementType.LEGACY_UPDATE,
                quantity_delta=on_hand - existing.quantity_on_hand,
                previous_on_hand=existing.quantity_on_hand,
                previous_available=existing.quantity_available,
                reservation_quantity=reserved + active_reservations,
                reason="Inventory quantity updated through the compatibility API",
                actor_id=values.actor_id,
                source="legacy_patch",
                reference_id=None,
            )
            INVENTORY_ADJUSTMENTS.inc()
            await self._publish(InventoryAdjusted, item)
        return item

    async def adjust_owned(
        self, inventory_id: UUID, actor_id: UUID, values: InventoryAdjustment
    ) -> InventoryItem:
        self._validate_adjustment(values)
        return await self._apply_quantity_operation(
            inventory_id,
            actor_id,
            expected_version=values.expected_version,
            quantity_delta=values.quantity_delta,
            physical_count=None,
            movement_type=values.movement_type,
            reason=values.reason,
            source=values.source,
            reference_id=values.reference_id,
        )

    async def reconcile_owned(
        self, inventory_id: UUID, actor_id: UUID, values: InventoryReconciliation
    ) -> InventoryItem:
        if values.physical_count < 0:
            raise _validation("physical_count", "Physical count must be non-negative.")
        self._validate_audit(values.reason, values.source)
        return await self._apply_quantity_operation(
            inventory_id,
            actor_id,
            expected_version=values.expected_version,
            quantity_delta=None,
            physical_count=values.physical_count,
            movement_type=InventoryMovementType.RECONCILIATION,
            reason=values.reason,
            source=values.source,
            reference_id=values.reference_id,
        )

    async def movement_history(
        self, actor_id: UUID, filters: InventoryMovementFilter
    ) -> tuple[Sequence[InventoryMovement], int]:
        return await self._movement_repository().list_for_operator(actor_id, filters)

    async def stock_by_classification(
        self, actor_id: UUID, filters: InventoryStockFilter
    ) -> tuple[Sequence[InventoryStock], int]:
        return await self._movement_repository().list_stock(
            actor_id, filters, datetime.now(UTC)
        )

    async def _apply_quantity_operation(
        self,
        inventory_id: UUID,
        actor_id: UUID,
        *,
        expected_version: int,
        quantity_delta: int | None,
        physical_count: int | None,
        movement_type: InventoryMovementType,
        reason: str,
        source: str,
        reference_id: UUID | None,
    ) -> InventoryItem:
        started = perf_counter()
        existing = await self._repository.get_locked_for_operator(
            inventory_id, actor_id
        )
        if existing is None:
            raise _not_found()
        if existing.version != expected_version:
            raise _conflict("The inventory item was modified by another request.")
        if existing.status is InventoryStatus.DISCONTINUED:
            raise _conflict("Discontinued Inventory cannot be adjusted.")
        now = datetime.now(UTC)
        active_reservations = await self._repository.active_reservation_quantity(
            inventory_id, now
        )
        new_on_hand = (
            physical_count
            if physical_count is not None
            else existing.quantity_on_hand + (quantity_delta or 0)
        )
        if new_on_hand < 0:
            raise _conflict("The adjustment would make on-hand quantity negative.")
        protected_quantity = existing.quantity_reserved + active_reservations
        if new_on_hand < protected_quantity:
            raise _conflict(
                "The adjustment would invalidate active Inventory Reservations."
            )
        delta = new_on_hand - existing.quantity_on_hand
        new_available = new_on_hand - existing.quantity_reserved
        new_status = (
            InventoryStatus.OUT_OF_STOCK
            if new_available == 0
            else InventoryStatus.ACTIVE
        )
        updated = await self._repository.update(
            inventory_id,
            actor_id,
            values={
                "quantity_on_hand": new_on_hand,
                "quantity_available": new_available,
                "status": new_status,
                "updated_by_id": actor_id,
            },
            expected_version=expected_version,
        )
        if updated is None:
            raise _conflict("The inventory item was modified by another request.")
        await self._record_movement(
            updated,
            movement_type=movement_type,
            quantity_delta=delta,
            previous_on_hand=existing.quantity_on_hand,
            previous_available=existing.quantity_available,
            reservation_quantity=protected_quantity,
            reason=reason,
            actor_id=actor_id,
            source=source,
            reference_id=reference_id,
        )
        INVENTORY_UPDATED.inc()
        INVENTORY_ADJUSTMENTS.inc()
        if movement_type is InventoryMovementType.RECONCILIATION:
            INVENTORY_RECONCILED.inc()
            await self._publish(InventoryReconciled, updated)
        else:
            await self._publish(InventoryAdjusted, updated)
        await self._publish_threshold_crossing(
            existing,
            updated,
            active_reservations=active_reservations,
        )
        INVENTORY_ADJUSTMENT_DURATION.observe(perf_counter() - started)
        return updated

    async def _publish_threshold_crossing(
        self,
        previous: InventoryItem,
        updated: InventoryItem,
        *,
        active_reservations: int,
    ) -> None:
        previous_effective = previous.quantity_available - active_reservations
        updated_effective = updated.quantity_available - active_reservations
        if previous_effective > 0 and updated_effective <= 0:
            INVENTORY_OUT_OF_STOCK.inc()
            await self._publish(InventoryOutOfStock, updated)
        elif (
            previous_effective > previous.low_stock_threshold
            and 0 < updated_effective <= updated.low_stock_threshold
        ):
            INVENTORY_LOW_STOCK.inc()
            await self._publish(InventoryLowStock, updated)

    async def _record_movement(
        self,
        item: InventoryItem,
        *,
        movement_type: InventoryMovementType,
        quantity_delta: int,
        previous_on_hand: int,
        previous_available: int,
        reservation_quantity: int,
        reason: str,
        actor_id: UUID,
        source: str,
        reference_id: UUID | None,
    ) -> InventoryMovement:
        return await self._movement_repository().add(
            {
                "inventory_id": item.id,
                "store_id": item.store_id,
                "variant_id": item.variant_id,
                "movement_type": movement_type,
                "quantity_delta": quantity_delta,
                "previous_on_hand": previous_on_hand,
                "new_on_hand": item.quantity_on_hand,
                "previous_available": previous_available,
                "new_available": item.quantity_available,
                "reservation_quantity": reservation_quantity,
                "reason": reason,
                "actor_id": actor_id,
                "source": source,
                "reference_id": reference_id,
            }
        )

    def _movement_repository(self) -> InventoryMovementRepository:
        if self._movements is None:
            raise RuntimeError("Inventory movement persistence is not configured")
        return self._movements

    @staticmethod
    def _validate_adjustment(values: InventoryAdjustment) -> None:
        InventoryService._validate_audit(values.reason, values.source)
        positive = {
            InventoryMovementType.MANUAL_INCREASE,
            InventoryMovementType.FOUND,
        }
        negative = {
            InventoryMovementType.MANUAL_DECREASE,
            InventoryMovementType.DAMAGE,
            InventoryMovementType.LOSS,
        }
        allowed = positive | negative | {InventoryMovementType.CORRECTION}
        if values.movement_type not in allowed:
            raise _validation("movement_type", "Movement type is not adjustable.")
        if values.quantity_delta == 0:
            raise _validation("quantity_delta", "Adjustment delta cannot be zero.")
        if values.movement_type in positive and values.quantity_delta < 0:
            raise _validation("quantity_delta", "This movement requires an increase.")
        if values.movement_type in negative and values.quantity_delta > 0:
            raise _validation("quantity_delta", "This movement requires a decrease.")

    @staticmethod
    def _validate_audit(reason: str, source: str) -> None:
        if not 1 <= len(reason.strip()) <= 500:
            raise _validation("reason", "Reason must contain 1 to 500 characters.")
        if not 1 <= len(source.strip()) <= 100:
            raise _validation("source", "Source must contain 1 to 100 characters.")

    async def delete_owned(
        self, inventory_id: UUID, owner_id: UUID, version: int
    ) -> None:
        await self.get_owned(inventory_id, owner_id)
        item = await self._repository.archive(
            inventory_id,
            owner_id,
            expected_version=version,
            deleted_at=datetime.now(UTC),
        )
        if item is None:
            raise _conflict("The inventory item was modified by another request.")
        INVENTORY_DELETED.inc()
        await self._publish(InventoryDeleted, item)

    async def _publish(
        self,
        event_type: (
            type[InventoryCreated]
            | type[InventoryUpdated]
            | type[InventoryDeleted]
            | type[InventoryAdjusted]
            | type[InventoryReconciled]
            | type[InventoryLowStock]
            | type[InventoryOutOfStock]
        ),
        item: InventoryItem,
    ) -> None:
        await self._events.publish(
            event_type(
                inventory_id=item.id,
                variant_id=item.variant_id,
                product_id=item.product_id,
                catalog_id=item.catalog_id,
                store_id=item.store_id,
                version=item.version,
            )
        )


class RetailerOperationsService:
    def __init__(self, repository: RetailerOperationsRepository) -> None:
        self._repository = repository

    async def summary(
        self, store_id: UUID, actor_id: UUID
    ) -> RetailerOperationsSummary:
        value = await self._repository.summary(store_id, actor_id, datetime.now(UTC))
        if value is None:
            raise _not_found()
        return value

    async def orders(
        self, actor_id: UUID, filters: RetailerActivityFilter
    ) -> tuple[Sequence[RetailerOrderActivity], int]:
        if not await self._repository.store_accessible(filters.store_id, actor_id):
            raise _not_found()
        return await self._repository.list_orders(actor_id, filters)

    async def shipments(
        self, actor_id: UUID, filters: RetailerActivityFilter
    ) -> tuple[Sequence[RetailerShipmentActivity], int]:
        if not await self._repository.store_accessible(filters.store_id, actor_id):
            raise _not_found()
        return await self._repository.list_shipments(actor_id, filters)


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Inventory validation failed",
        detail="Inventory fields are invalid.",
        status_code=422,
        errors=[
            FieldError(field=field, code="invalid_inventory_field", message=message)
        ],
    )


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Inventory not found",
        detail="The requested inventory item was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Inventory conflict",
        detail=detail,
        status_code=409,
    )
