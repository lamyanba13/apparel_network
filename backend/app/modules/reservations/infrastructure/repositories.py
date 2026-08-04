from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.products.domain import OutboxStatus
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.reservations.application.schemas import ReservationFilter
from app.modules.reservations.domain import (
    InventoryReservation,
    ReservationEvent,
    ReservationItem,
    ReservationStatus,
)
from app.modules.reservations.infrastructure.models import (
    InventoryReservationItemModel,
    InventoryReservationModel,
)


class SqlAlchemyReservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_for_order(self, order_id: UUID) -> InventoryReservation | None:
        model = await self._session.scalar(
            select(InventoryReservationModel).where(
                InventoryReservationModel.order_id == order_id,
                InventoryReservationModel.status == ReservationStatus.ACTIVE,
                InventoryReservationModel.deleted_at.is_(None),
            )
        )
        return _reservation(model) if model else None

    async def add(self, values: Mapping[str, object]) -> InventoryReservation:
        model = InventoryReservationModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _reservation(model)

    async def list_for_customer(
        self, customer_id: UUID, filters: ReservationFilter
    ) -> tuple[Sequence[InventoryReservation], int]:
        query = select(InventoryReservationModel).where(
            InventoryReservationModel.customer_id == customer_id,
            InventoryReservationModel.deleted_at.is_(None),
        )
        if filters.store_id is not None:
            query = query.where(InventoryReservationModel.store_id == filters.store_id)
        if filters.order_id is not None:
            query = query.where(InventoryReservationModel.order_id == filters.order_id)
        if filters.status is not None:
            query = query.where(InventoryReservationModel.status == filters.status)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(
                    InventoryReservationModel.created_at.desc(),
                    InventoryReservationModel.id,
                )
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_reservation(row) for row in rows], total

    async def get_for_customer(
        self, reservation_id: UUID, customer_id: UUID
    ) -> InventoryReservation | None:
        model = await self._model(reservation_id, customer_id)
        return _reservation(model) if model else None

    async def transition(
        self,
        reservation_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: ReservationStatus,
        transitioned_at: datetime,
        actor_id: UUID,
        archive: bool = False,
    ) -> InventoryReservation | None:
        model = await self._model(reservation_id, customer_id, expected_version)
        if model is None:
            return None
        model.status = status
        if status is ReservationStatus.RELEASED:
            model.released_at = transitioned_at
        elif status is ReservationStatus.CONSUMED:
            model.consumed_at = transitioned_at
        if archive:
            model.deleted_at = transitioned_at
            model.deleted_by_id = actor_id
        model.updated_by_id = actor_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _reservation(model)

    async def _model(
        self, reservation_id: UUID, customer_id: UUID, version: int | None = None
    ) -> InventoryReservationModel | None:
        query = select(InventoryReservationModel).where(
            InventoryReservationModel.id == reservation_id,
            InventoryReservationModel.customer_id == customer_id,
            InventoryReservationModel.deleted_at.is_(None),
        )
        if version is not None:
            query = query.where(InventoryReservationModel.version == version)
        model: InventoryReservationModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyReservationItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_quantity(self, inventory_item_id: UUID, now: datetime) -> int:
        value = await self._session.scalar(
            select(func.coalesce(func.sum(InventoryReservationItemModel.quantity), 0))
            .join(InventoryReservationModel)
            .where(
                InventoryReservationItemModel.inventory_item_id == inventory_item_id,
                InventoryReservationModel.status == ReservationStatus.ACTIVE,
                InventoryReservationModel.expires_at > now,
                InventoryReservationModel.deleted_at.is_(None),
            )
        )
        return int(value or 0)

    async def add_many(
        self, values: Sequence[Mapping[str, object]]
    ) -> Sequence[ReservationItem]:
        models = [InventoryReservationItemModel(**dict(value)) for value in values]
        self._session.add_all(models)
        await self._session.flush()
        for model in models:
            await self._session.refresh(model)
        return [_item(model) for model in models]

    async def list_for_reservation(
        self, reservation_id: UUID
    ) -> Sequence[ReservationItem]:
        rows = (
            await self._session.scalars(
                select(InventoryReservationItemModel)
                .where(InventoryReservationItemModel.reservation_id == reservation_id)
                .order_by(
                    InventoryReservationItemModel.created_at,
                    InventoryReservationItemModel.id,
                )
            )
        ).all()
        return [_item(row) for row in rows]


class SqlAlchemyReservationOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: ReservationEvent) -> None:
        self._session.add(
            EventOutboxModel(
                id=event.event_id,
                aggregate_type="reservation",
                aggregate_id=event.reservation_id,
                event_name=event.event_name,
                payload=cast(dict[str, object], event.payload),
                occurred_at=event.occurred_at,
                status=OutboxStatus.PENDING,
            )
        )
        await self._session.flush()


def _reservation(model: InventoryReservationModel) -> InventoryReservation:
    return InventoryReservation(
        id=model.id,
        order_id=model.order_id,
        payment_id=model.payment_id,
        customer_id=model.customer_id,
        store_id=model.store_id,
        status=model.status,
        expires_at=model.expires_at,
        released_at=model.released_at,
        consumed_at=model.consumed_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _item(model: InventoryReservationItemModel) -> ReservationItem:
    return ReservationItem(
        id=model.id,
        reservation_id=model.reservation_id,
        inventory_item_id=model.inventory_item_id,
        variant_id=model.variant_id,
        quantity=model.quantity,
        inventory_version=model.inventory_version,
        created_at=model.created_at,
    )
