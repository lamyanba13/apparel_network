from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.products.domain import OutboxStatus
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.shipments.application.schemas import ShipmentFilter
from app.modules.shipments.domain import (
    Shipment,
    ShipmentEvent,
    ShipmentPackage,
    ShipmentStatus,
    ShipmentTrackingEvent,
)
from app.modules.shipments.infrastructure.models import (
    ShipmentModel,
    ShipmentPackageModel,
    ShipmentTrackingEventModel,
)


class SqlAlchemyShipmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, values: Mapping[str, object]) -> Shipment:
        model = ShipmentModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _shipment(model)

    async def get_for_order(self, order_id: UUID) -> Shipment | None:
        model = await self._session.scalar(
            select(ShipmentModel).where(ShipmentModel.order_id == order_id)
        )
        return _shipment(model) if model else None

    async def get_for_customer(
        self, shipment_id: UUID, customer_id: UUID
    ) -> Shipment | None:
        model = await self._model(shipment_id, customer_id)
        return _shipment(model) if model else None

    async def list_for_customer(
        self, customer_id: UUID, filters: ShipmentFilter
    ) -> tuple[Sequence[Shipment], int]:
        query = select(ShipmentModel).where(
            ShipmentModel.customer_id == customer_id,
            ShipmentModel.deleted_at.is_(None),
        )
        if filters.store_id is not None:
            query = query.where(ShipmentModel.store_id == filters.store_id)
        if filters.order_id is not None:
            query = query.where(ShipmentModel.order_id == filters.order_id)
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
                query.order_by(ShipmentModel.created_at.desc(), ShipmentModel.id)
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_shipment(row) for row in rows], total

    async def transition(
        self,
        shipment_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: ShipmentStatus,
        actor_id: UUID,
        transitioned_at: datetime,
        values: Mapping[str, object] | None = None,
        archive: bool = False,
    ) -> Shipment | None:
        model = await self._model(shipment_id, customer_id, expected_version)
        if model is None:
            return None
        model.status = status
        for key, value in (values or {}).items():
            setattr(model, key, value)
        if status is ShipmentStatus.SHIPPED:
            model.shipped_at = transitioned_at
        elif status is ShipmentStatus.DELIVERED:
            model.delivered_at = transitioned_at
        if archive:
            model.deleted_at = transitioned_at
            model.deleted_by_id = actor_id
        model.updated_by_id = actor_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _shipment(model)

    async def _model(
        self, shipment_id: UUID, customer_id: UUID, version: int | None = None
    ) -> ShipmentModel | None:
        query = select(ShipmentModel).where(
            ShipmentModel.id == shipment_id,
            ShipmentModel.customer_id == customer_id,
            ShipmentModel.deleted_at.is_(None),
        )
        if version is not None:
            query = query.where(ShipmentModel.version == version)
        model: ShipmentModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyShipmentPackageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(
        self, values: Sequence[Mapping[str, object]]
    ) -> Sequence[ShipmentPackage]:
        models = [ShipmentPackageModel(**dict(value)) for value in values]
        self._session.add_all(models)
        await self._session.flush()
        for model in models:
            await self._session.refresh(model)
        return [_package(model) for model in models]

    async def list_for_shipment(self, shipment_id: UUID) -> Sequence[ShipmentPackage]:
        rows = (
            await self._session.scalars(
                select(ShipmentPackageModel)
                .where(ShipmentPackageModel.shipment_id == shipment_id)
                .order_by(ShipmentPackageModel.package_number, ShipmentPackageModel.id)
            )
        ).all()
        return [_package(row) for row in rows]


class SqlAlchemyShipmentTrackingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        shipment_id: UUID,
        status: ShipmentStatus,
        description: str,
        occurred_at: datetime,
        location: str | None = None,
    ) -> ShipmentTrackingEvent:
        model = ShipmentTrackingEventModel(
            shipment_id=shipment_id,
            status=status,
            location=location,
            description=description,
            occurred_at=occurred_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _tracking(model)

    async def list_for_shipment(
        self, shipment_id: UUID
    ) -> Sequence[ShipmentTrackingEvent]:
        rows = (
            await self._session.scalars(
                select(ShipmentTrackingEventModel)
                .where(ShipmentTrackingEventModel.shipment_id == shipment_id)
                .order_by(
                    ShipmentTrackingEventModel.occurred_at,
                    ShipmentTrackingEventModel.id,
                )
            )
        ).all()
        return [_tracking(row) for row in rows]


class SqlAlchemyShipmentOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: ShipmentEvent) -> None:
        self._session.add(
            EventOutboxModel(
                id=event.event_id,
                aggregate_type="shipment",
                aggregate_id=event.shipment_id,
                event_name=event.event_name,
                payload=cast(dict[str, object], event.payload),
                occurred_at=event.occurred_at,
                status=OutboxStatus.PENDING,
            )
        )
        await self._session.flush()


def _shipment(model: ShipmentModel) -> Shipment:
    return Shipment(
        id=model.id,
        order_id=model.order_id,
        reservation_id=model.reservation_id,
        payment_id=model.payment_id,
        customer_id=model.customer_id,
        store_id=model.store_id,
        status=model.status,
        carrier=model.carrier,
        tracking_number=model.tracking_number,
        tracking_url=model.tracking_url,
        shipping_method=model.shipping_method,
        estimated_delivery_at=model.estimated_delivery_at,
        shipped_at=model.shipped_at,
        delivered_at=model.delivered_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _package(model: ShipmentPackageModel) -> ShipmentPackage:
    return ShipmentPackage(
        id=model.id,
        shipment_id=model.shipment_id,
        package_number=model.package_number,
        weight=model.weight,
        length=model.length,
        width=model.width,
        height=model.height,
        label_url=model.label_url,
        created_at=model.created_at,
    )


def _tracking(model: ShipmentTrackingEventModel) -> ShipmentTrackingEvent:
    return ShipmentTrackingEvent(
        id=model.id,
        shipment_id=model.shipment_id,
        status=model.status,
        location=model.location,
        description=model.description,
        occurred_at=model.occurred_at,
    )
