from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.application.schemas import OrderFilter
from app.modules.orders.domain import Order, OrderEvent, OrderItem, OrderStatus
from app.modules.orders.infrastructure.models import (
    ORDER_NUMBER_SEQUENCE,
    OrderItemModel,
    OrderModel,
)
from app.modules.products.domain import OutboxStatus
from app.modules.products.infrastructure.attribute_models import EventOutboxModel


class SqlAlchemyOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def next_number_value(self) -> int:
        value = await self._session.scalar(select(ORDER_NUMBER_SEQUENCE.next_value()))
        if value is None:
            raise RuntimeError("Order number sequence did not return a value")
        return int(value)

    async def exists_for_checkout(self, checkout_id: UUID) -> bool:
        return (
            await self._session.scalar(
                select(OrderModel.id).where(
                    OrderModel.checkout_session_id == checkout_id
                )
            )
            is not None
        )

    async def add(self, values: Mapping[str, object]) -> Order:
        model = OrderModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _order(model)

    async def list_for_customer(
        self, customer_id: UUID, filters: OrderFilter
    ) -> tuple[Sequence[Order], int]:
        query = select(OrderModel).where(
            OrderModel.customer_id == customer_id,
            OrderModel.deleted_at.is_(None),
        )
        if filters.store_id is not None:
            query = query.where(OrderModel.store_id == filters.store_id)
        if filters.status is not None:
            query = query.where(OrderModel.status == filters.status)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(OrderModel.placed_at.desc(), OrderModel.id)
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_order(row) for row in rows], total

    async def get_for_customer(self, order_id: UUID, customer_id: UUID) -> Order | None:
        model = await self._model(order_id, customer_id)
        return _order(model) if model else None

    async def transition(
        self,
        order_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: OrderStatus,
        transitioned_at: datetime,
        actor_id: UUID,
    ) -> Order | None:
        model = await self._model(order_id, customer_id, expected_version)
        if model is None or model.status is not OrderStatus.PENDING:
            return None
        model.status = status
        model.confirmed_at = transitioned_at
        model.updated_by_id = actor_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _order(model)

    async def archive(
        self,
        order_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> Order | None:
        model = await self._model(order_id, customer_id, expected_version)
        if model is None or model.status is not OrderStatus.CONFIRMED:
            return None
        model.status = OrderStatus.CANCELLED
        model.cancelled_at = deleted_at
        model.deleted_at = deleted_at
        model.deleted_by_id = deleted_by_id
        model.updated_by_id = deleted_by_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _order(model)

    async def _model(
        self, order_id: UUID, customer_id: UUID, version: int | None = None
    ) -> OrderModel | None:
        query = select(OrderModel).where(
            OrderModel.id == order_id,
            OrderModel.customer_id == customer_id,
            OrderModel.deleted_at.is_(None),
        )
        if version is not None:
            query = query.where(OrderModel.version == version)
        model: OrderModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyOrderItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(
        self, values: Sequence[Mapping[str, object]]
    ) -> Sequence[OrderItem]:
        models = [OrderItemModel(**dict(value)) for value in values]
        self._session.add_all(models)
        await self._session.flush()
        for model in models:
            await self._session.refresh(model)
        return [_item(model) for model in models]

    async def list_for_order(self, order_id: UUID) -> Sequence[OrderItem]:
        rows = (
            await self._session.scalars(
                select(OrderItemModel)
                .where(OrderItemModel.order_id == order_id)
                .order_by(OrderItemModel.created_at, OrderItemModel.id)
            )
        ).all()
        return [_item(row) for row in rows]


class SqlAlchemyOrderOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: OrderEvent) -> None:
        self._session.add(
            EventOutboxModel(
                id=event.event_id,
                aggregate_type="order",
                aggregate_id=event.order_id,
                event_name=event.event_name,
                payload=cast(dict[str, object], event.payload),
                occurred_at=event.occurred_at,
                status=OutboxStatus.PENDING,
            )
        )
        await self._session.flush()


def _order(model: OrderModel) -> Order:
    return Order(
        id=model.id,
        checkout_session_id=model.checkout_session_id,
        cart_id=model.cart_id,
        store_id=model.store_id,
        customer_id=model.customer_id,
        order_number=model.order_number,
        status=model.status,
        currency=model.currency,
        subtotal=model.subtotal,
        placed_at=model.placed_at,
        confirmed_at=model.confirmed_at,
        cancelled_at=model.cancelled_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _item(model: OrderItemModel) -> OrderItem:
    return OrderItem(
        id=model.id,
        order_id=model.order_id,
        product_id=model.product_id,
        variant_id=model.variant_id,
        quantity=model.quantity,
        price_id=model.price_id,
        unit_price=model.unit_price,
        currency=model.currency,
        inventory_id=model.inventory_id,
        inventory_version=model.inventory_version,
        snapshot_timestamp=model.snapshot_timestamp,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
    )
