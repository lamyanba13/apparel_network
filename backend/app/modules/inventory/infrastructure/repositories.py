from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from app.modules.inventory.application.schemas import (
    InventoryMovementFilter,
    InventoryStockFilter,
    RetailerActivityFilter,
)
from app.modules.inventory.domain import (
    InventoryItem,
    InventoryMovement,
    InventoryStatus,
    InventoryStock,
    RetailerOperationsSummary,
    RetailerOrderActivity,
    RetailerShipmentActivity,
    StockClassification,
)
from app.modules.inventory.infrastructure.models import (
    InventoryItemModel,
    InventoryMovementModel,
)
from app.modules.orders.domain import OrderStatus
from app.modules.orders.infrastructure.models import OrderModel
from app.modules.products.domain import ProductStatus
from app.modules.products.infrastructure.models import ProductModel
from app.modules.products.infrastructure.variant_models import ProductVariantModel
from app.modules.reservations.domain import ReservationStatus
from app.modules.reservations.infrastructure.models import (
    InventoryReservationItemModel,
    InventoryReservationModel,
)
from app.modules.shipments.domain import ShipmentStatus
from app.modules.shipments.infrastructure.models import ShipmentModel
from app.modules.stores.infrastructure.persistence.access import store_accessible_by
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyInventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def variant_context(
        self, variant_id: UUID, owner_id: UUID
    ) -> Mapping[str, object] | None:
        row = await self._session.execute(
            select(
                ProductVariantModel.product_id,
                ProductModel.catalog_id,
                ProductModel.store_id,
                ProductVariantModel.reference,
            )
            .join(ProductModel, ProductModel.id == ProductVariantModel.product_id)
            .join(StoreModel, StoreModel.id == ProductModel.store_id)
            .where(
                ProductVariantModel.id == variant_id,
                ProductVariantModel.deleted_at.is_(None),
                ProductVariantModel.is_active.is_(True),
                ProductModel.deleted_at.is_(None),
                store_accessible_by(owner_id),
            )
        )
        value = row.one_or_none()
        if value is None:
            return None
        return {
            "product_id": value.product_id,
            "catalog_id": value.catalog_id,
            "store_id": value.store_id,
            "reference": value.reference,
        }

    async def variant_has_inventory(self, variant_id: UUID) -> bool:
        return (
            await self._session.scalar(
                select(InventoryItemModel.id).where(
                    InventoryItemModel.variant_id == variant_id
                )
            )
            is not None
        )

    async def add(self, values: Mapping[str, object]) -> InventoryItem:
        model = InventoryItemModel(
            **{
                key: value
                for key, value in values.items()
                if key not in {"actor_id", "reference"}
            }
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def list_for_owner(
        self, owner_id: UUID, **filters: object
    ) -> tuple[Sequence[InventoryItem], int]:
        query = (
            select(InventoryItemModel)
            .join(StoreModel)
            .where(
                store_accessible_by(owner_id),
                InventoryItemModel.deleted_at.is_(None),
            )
        )
        for field in ("store_id", "catalog_id", "product_id", "variant_id", "status"):
            value = filters.get(field)
            if value is not None:
                query = query.where(getattr(InventoryItemModel, field) == value)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(
                    InventoryItemModel.updated_at.desc(), InventoryItemModel.id
                )
                .offset(cast(int, filters["offset"]))
                .limit(cast(int, filters["limit"]))
            )
        ).all()
        return [_to_domain(row) for row in rows], total

    async def get_for_owner(
        self, inventory_id: UUID, owner_id: UUID
    ) -> InventoryItem | None:
        model = await self._session.scalar(
            select(InventoryItemModel)
            .join(StoreModel)
            .where(
                InventoryItemModel.id == inventory_id,
                InventoryItemModel.deleted_at.is_(None),
                store_accessible_by(owner_id),
            )
        )
        return _to_domain(model) if model else None

    async def get_locked_for_operator(
        self, inventory_id: UUID, actor_id: UUID
    ) -> InventoryItem | None:
        model = await self._session.scalar(
            select(InventoryItemModel)
            .join(StoreModel)
            .where(
                InventoryItemModel.id == inventory_id,
                InventoryItemModel.deleted_at.is_(None),
                store_accessible_by(actor_id),
            )
            .with_for_update()
        )
        return _to_domain(model) if model else None

    async def active_reservation_quantity(
        self, inventory_id: UUID, now: datetime
    ) -> int:
        value = await self._session.scalar(
            select(func.coalesce(func.sum(InventoryReservationItemModel.quantity), 0))
            .join(InventoryReservationModel)
            .where(
                InventoryReservationItemModel.inventory_item_id == inventory_id,
                InventoryReservationModel.status == ReservationStatus.ACTIVE,
                InventoryReservationModel.expires_at > now,
                InventoryReservationModel.deleted_at.is_(None),
            )
        )
        return int(value or 0)

    async def get_for_store(
        self, inventory_id: UUID, store_id: UUID
    ) -> InventoryItem | None:
        model = await self._session.scalar(
            select(InventoryItemModel)
            .where(
                InventoryItemModel.id == inventory_id,
                InventoryItemModel.store_id == store_id,
                InventoryItemModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return _to_domain(model) if model else None

    async def update(
        self,
        inventory_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> InventoryItem | None:
        model = await self._session.scalar(
            select(InventoryItemModel)
            .join(StoreModel)
            .where(
                InventoryItemModel.id == inventory_id,
                InventoryItemModel.deleted_at.is_(None),
                InventoryItemModel.version == expected_version,
                store_accessible_by(owner_id),
            )
            .with_for_update()
        )
        if model is None:
            return None
        for key, value in values.items():
            setattr(model, key, value)
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def consume(
        self,
        inventory_id: UUID,
        store_id: UUID,
        *,
        quantity: int,
        actor_id: UUID,
        expected_version: int,
    ) -> InventoryItem | None:
        model = await self._session.scalar(
            select(InventoryItemModel)
            .where(
                InventoryItemModel.id == inventory_id,
                InventoryItemModel.store_id == store_id,
                InventoryItemModel.deleted_at.is_(None),
                InventoryItemModel.version == expected_version,
            )
            .with_for_update()
        )
        if model is None or model.quantity_available < quantity:
            return None
        model.quantity_on_hand -= quantity
        model.quantity_available = model.quantity_on_hand - model.quantity_reserved
        model.updated_by_id = actor_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def archive(
        self,
        inventory_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
    ) -> InventoryItem | None:
        model = await self._session.scalar(
            select(InventoryItemModel)
            .join(StoreModel)
            .where(
                InventoryItemModel.id == inventory_id,
                InventoryItemModel.deleted_at.is_(None),
                InventoryItemModel.version == expected_version,
                store_accessible_by(owner_id),
            )
            .with_for_update()
        )
        if model is None:
            return None
        model.deleted_at, model.status, model.updated_by_id = (
            deleted_at,
            InventoryStatus.DISCONTINUED,
            owner_id,
        )
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)


class SqlAlchemyInventoryMovementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, values: Mapping[str, object]) -> InventoryMovement:
        model = InventoryMovementModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _movement(model)

    async def list_for_operator(
        self, actor_id: UUID, filters: InventoryMovementFilter
    ) -> tuple[Sequence[InventoryMovement], int]:
        query = (
            select(InventoryMovementModel)
            .join(StoreModel, StoreModel.id == InventoryMovementModel.store_id)
            .where(store_accessible_by(actor_id))
        )
        for field in (
            "store_id",
            "inventory_id",
            "variant_id",
            "movement_type",
            "actor_id",
            "source",
            "reference_id",
        ):
            value = getattr(filters, field)
            if value is not None:
                query = query.where(getattr(InventoryMovementModel, field) == value)
        if filters.created_from is not None:
            query = query.where(
                InventoryMovementModel.created_at >= filters.created_from
            )
        if filters.created_to is not None:
            query = query.where(InventoryMovementModel.created_at <= filters.created_to)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(
                    InventoryMovementModel.created_at.desc(),
                    InventoryMovementModel.id.desc(),
                )
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_movement(row) for row in rows], total

    async def list_stock(
        self, actor_id: UUID, filters: InventoryStockFilter, now: datetime
    ) -> tuple[Sequence[InventoryStock], int]:
        active_reserved = _active_reservation_subquery(now)
        effective = InventoryItemModel.quantity_available - active_reserved
        query = (
            select(
                InventoryItemModel,
                active_reserved.label("active_reservation_quantity"),
            )
            .join(StoreModel, StoreModel.id == InventoryItemModel.store_id)
            .where(
                store_accessible_by(actor_id),
                InventoryItemModel.deleted_at.is_(None),
                InventoryItemModel.status != InventoryStatus.DISCONTINUED,
            )
        )
        if filters.store_id is not None:
            query = query.where(InventoryItemModel.store_id == filters.store_id)
        query = query.where(_stock_condition(filters.classification, effective))
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.execute(
                query.order_by(
                    effective,
                    InventoryItemModel.updated_at.desc(),
                    InventoryItemModel.id,
                )
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [
            _stock(model, int(reserved), filters.classification)
            for model, reserved in rows
        ], total


class SqlAlchemyRetailerOperationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store_accessible(self, store_id: UUID, actor_id: UUID) -> bool:
        return (
            await self._session.scalar(
                select(StoreModel.id).where(
                    StoreModel.id == store_id,
                    StoreModel.deleted_at.is_(None),
                    store_accessible_by(actor_id),
                )
            )
            is not None
        )

    async def summary(
        self, store_id: UUID, actor_id: UUID, now: datetime
    ) -> RetailerOperationsSummary | None:
        if not await self.store_accessible(store_id, actor_id):
            return None
        active_reserved = _active_reservation_subquery(now)
        effective = InventoryItemModel.quantity_available - active_reserved
        inventory_base = and_(
            InventoryItemModel.store_id == store_id,
            InventoryItemModel.deleted_at.is_(None),
            InventoryItemModel.status != InventoryStatus.DISCONTINUED,
        )
        active_products = await self._count(
            select(ProductModel.id).where(
                ProductModel.store_id == store_id,
                ProductModel.status != ProductStatus.ARCHIVED,
                ProductModel.deleted_at.is_(None),
            )
        )
        active_variants = await self._count(
            select(ProductVariantModel.id).where(
                ProductVariantModel.store_id == store_id,
                ProductVariantModel.is_active.is_(True),
                ProductVariantModel.deleted_at.is_(None),
            )
        )
        in_stock = await self._count(
            select(InventoryItemModel.id).where(inventory_base, effective > 0)
        )
        low_stock = await self._count(
            select(InventoryItemModel.id).where(
                inventory_base,
                effective > 0,
                effective <= InventoryItemModel.low_stock_threshold,
            )
        )
        out_of_stock = await self._count(
            select(InventoryItemModel.id).where(inventory_base, effective <= 0)
        )
        orders_awaiting = await self._count(
            select(OrderModel.id)
            .outerjoin(ShipmentModel, ShipmentModel.order_id == OrderModel.id)
            .where(
                OrderModel.store_id == store_id,
                OrderModel.status == OrderStatus.CONFIRMED,
                OrderModel.deleted_at.is_(None),
                ShipmentModel.id.is_(None),
            )
        )
        orders_attention = await self._count(
            select(OrderModel.id).where(
                OrderModel.store_id == store_id,
                OrderModel.status == OrderStatus.PENDING,
                OrderModel.deleted_at.is_(None),
            )
        )
        shipments_pending = await self._count(
            select(ShipmentModel.id).where(
                ShipmentModel.store_id == store_id,
                ShipmentModel.status.in_(
                    (
                        ShipmentStatus.CREATED,
                        ShipmentStatus.READY_FOR_FULFILLMENT,
                        ShipmentStatus.PACKED,
                    )
                ),
                ShipmentModel.deleted_at.is_(None),
            )
        )
        shipments_in_transit = await self._count(
            select(ShipmentModel.id).where(
                ShipmentModel.store_id == store_id,
                ShipmentModel.status.in_(
                    (ShipmentStatus.SHIPPED, ShipmentStatus.OUT_FOR_DELIVERY)
                ),
                ShipmentModel.deleted_at.is_(None),
            )
        )
        movements = (
            await self._session.scalars(
                select(InventoryMovementModel)
                .where(InventoryMovementModel.store_id == store_id)
                .order_by(
                    InventoryMovementModel.created_at.desc(),
                    InventoryMovementModel.id.desc(),
                )
                .limit(10)
            )
        ).all()
        return RetailerOperationsSummary(
            store_id=store_id,
            active_products=active_products,
            active_variants=active_variants,
            in_stock_variants=in_stock,
            low_stock_variants=low_stock,
            out_of_stock_variants=out_of_stock,
            orders_awaiting_fulfillment=orders_awaiting,
            orders_requiring_attention=orders_attention,
            shipments_pending_fulfillment=shipments_pending,
            shipments_in_transit=shipments_in_transit,
            recent_movements=tuple(_movement(value) for value in movements),
        )

    async def list_orders(
        self, actor_id: UUID, filters: RetailerActivityFilter
    ) -> tuple[Sequence[RetailerOrderActivity], int]:
        query = (
            select(OrderModel, ShipmentModel.status)
            .join(StoreModel, StoreModel.id == OrderModel.store_id)
            .outerjoin(ShipmentModel, ShipmentModel.order_id == OrderModel.id)
            .where(
                OrderModel.store_id == filters.store_id,
                OrderModel.deleted_at.is_(None),
                store_accessible_by(actor_id),
            )
        )
        if filters.status is not None:
            query = query.where(OrderModel.status == filters.status)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.execute(
                query.order_by(OrderModel.placed_at.desc(), OrderModel.id.desc())
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [
            RetailerOrderActivity(
                id=order.id,
                store_id=order.store_id,
                order_number=order.order_number,
                status=order.status.value,
                placed_at=order.placed_at,
                shipment_status=(shipment_status.value if shipment_status else None),
            )
            for order, shipment_status in rows
        ], total

    async def list_shipments(
        self, actor_id: UUID, filters: RetailerActivityFilter
    ) -> tuple[Sequence[RetailerShipmentActivity], int]:
        query = (
            select(ShipmentModel)
            .join(StoreModel, StoreModel.id == ShipmentModel.store_id)
            .where(
                ShipmentModel.store_id == filters.store_id,
                ShipmentModel.deleted_at.is_(None),
                store_accessible_by(actor_id),
            )
        )
        if filters.status is not None:
            query = query.where(ShipmentModel.status == filters.status)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(ShipmentModel.created_at.desc(), ShipmentModel.id.desc())
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [
            RetailerShipmentActivity(
                id=value.id,
                store_id=value.store_id,
                order_id=value.order_id,
                status=value.status.value,
                created_at=value.created_at,
            )
            for value in rows
        ], total

    async def _count(self, query: Select[Any]) -> int:
        return int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )


def _to_domain(model: InventoryItemModel) -> InventoryItem:
    return InventoryItem(
        id=model.id,
        variant_id=model.variant_id,
        product_id=model.product_id,
        catalog_id=model.catalog_id,
        store_id=model.store_id,
        sku_snapshot=model.sku_snapshot,
        quantity_on_hand=model.quantity_on_hand,
        quantity_reserved=model.quantity_reserved,
        quantity_available=model.quantity_available,
        status=model.status,
        tracking_policy=model.tracking_policy,
        low_stock_threshold=model.low_stock_threshold,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        version=model.version,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
    )


def _movement(model: InventoryMovementModel) -> InventoryMovement:
    return InventoryMovement(
        id=model.id,
        inventory_id=model.inventory_id,
        store_id=model.store_id,
        variant_id=model.variant_id,
        movement_type=model.movement_type,
        quantity_delta=model.quantity_delta,
        previous_on_hand=model.previous_on_hand,
        new_on_hand=model.new_on_hand,
        previous_available=model.previous_available,
        new_available=model.new_available,
        reservation_quantity=model.reservation_quantity,
        reason=model.reason,
        actor_id=model.actor_id,
        source=model.source,
        reference_id=model.reference_id,
        created_at=model.created_at,
    )


def _active_reservation_subquery(now: datetime) -> ColumnElement[int]:
    return (
        select(func.coalesce(func.sum(InventoryReservationItemModel.quantity), 0))
        .join(InventoryReservationModel)
        .where(
            InventoryReservationItemModel.inventory_item_id == InventoryItemModel.id,
            InventoryReservationModel.status == ReservationStatus.ACTIVE,
            InventoryReservationModel.expires_at > now,
            InventoryReservationModel.deleted_at.is_(None),
        )
        .correlate(InventoryItemModel)
        .scalar_subquery()
    )


def _stock_condition(
    classification: StockClassification, effective: ColumnElement[int]
) -> ColumnElement[bool]:
    if classification is StockClassification.OUT_OF_STOCK:
        return effective <= 0
    if classification is StockClassification.LOW_STOCK:
        return and_(effective > 0, effective <= InventoryItemModel.low_stock_threshold)
    return effective > InventoryItemModel.low_stock_threshold


def _stock(
    model: InventoryItemModel,
    active_reservation_quantity: int,
    classification: StockClassification,
) -> InventoryStock:
    return InventoryStock(
        inventory=_to_domain(model),
        active_reservation_quantity=active_reservation_quantity,
        effective_available=model.quantity_available - active_reservation_quantity,
        classification=classification,
    )
