from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.inventory.application.repositories import InventoryRepository
from app.modules.inventory.application.schemas import InventoryCreate, InventoryUpdate
from app.modules.inventory.domain import (
    InventoryAdjusted,
    InventoryCreated,
    InventoryDeleted,
    InventoryItem,
    InventoryStatus,
    InventoryUpdated,
    TrackingPolicy,
)
from app.observability.metrics import (
    INVENTORY_ADJUSTMENTS,
    INVENTORY_CREATED,
    INVENTORY_DELETED,
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
    def __init__(self, repository: InventoryRepository, events: EventPublisher) -> None:
        self._repository, self._events = repository, events
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

    async def update_owned(
        self, inventory_id: UUID, owner_id: UUID, values: InventoryUpdate
    ) -> InventoryItem:
        existing = await self.get_owned(inventory_id, owner_id)
        changes = self._validation.changes(values.values)
        on_hand_value = changes.get("quantity_on_hand", existing.quantity_on_hand)
        reserved_value = changes.get("quantity_reserved", existing.quantity_reserved)
        if not isinstance(on_hand_value, int) or not isinstance(reserved_value, int):
            raise _validation("quantity", "Quantity must be non-negative.")
        on_hand, reserved = on_hand_value, reserved_value
        self._validation.quantities(
            {"quantity_on_hand": on_hand, "quantity_reserved": reserved}
        )
        changes["quantity_available"] = on_hand - reserved
        item = await self._repository.update(
            inventory_id,
            owner_id,
            values={**changes, "updated_by_id": owner_id},
            expected_version=values.expected_version,
        )
        if item is None:
            raise _conflict("The inventory item was modified by another request.")
        INVENTORY_UPDATED.inc()
        await self._publish(InventoryUpdated, item)
        if (
            on_hand != existing.quantity_on_hand
            or reserved != existing.quantity_reserved
        ):
            INVENTORY_ADJUSTMENTS.inc()
            await self._publish(InventoryAdjusted, item)
        return item

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
