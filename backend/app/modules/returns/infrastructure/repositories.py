from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.products.domain import OutboxStatus
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.returns.application.schemas import RefundFilter, ReturnFilter
from app.modules.returns.domain import (
    InventoryDisposition,
    ProductReturn,
    Refund,
    RefundEvent,
    RefundStatus,
    RefundTransaction,
    ReturnEvent,
    ReturnItem,
    ReturnStatus,
)
from app.modules.returns.infrastructure.models import (
    RefundModel,
    RefundTransactionModel,
    ReturnItemModel,
    ReturnModel,
)


class SqlAlchemyReturnRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, values: Mapping[str, object]) -> ProductReturn:
        model = ReturnModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _return(model)

    async def get_for_customer(
        self, return_id: UUID, customer_id: UUID
    ) -> ProductReturn | None:
        model = await self._model(return_id, customer_id)
        return _return(model) if model else None

    async def list_for_customer(
        self, customer_id: UUID, filters: ReturnFilter
    ) -> tuple[Sequence[ProductReturn], int]:
        query = select(ReturnModel).where(
            ReturnModel.customer_id == customer_id, ReturnModel.deleted_at.is_(None)
        )
        if filters.store_id is not None:
            query = query.where(ReturnModel.store_id == filters.store_id)
        if filters.order_id is not None:
            query = query.where(ReturnModel.order_id == filters.order_id)
        if filters.status is not None:
            query = query.where(ReturnModel.status == filters.status)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(ReturnModel.created_at.desc(), ReturnModel.id)
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_return(row) for row in rows], total

    async def update_reason(
        self,
        return_id: UUID,
        customer_id: UUID,
        *,
        reason: str,
        expected_version: int,
        actor_id: UUID,
    ) -> ProductReturn | None:
        model = await self._model(return_id, customer_id, expected_version)
        if model is None:
            return None
        model.reason = reason
        model.updated_by_id = actor_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _return(model)

    async def transition(
        self,
        return_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: ReturnStatus,
        transitioned_at: datetime,
        actor_id: UUID,
        archive: bool = False,
    ) -> ProductReturn | None:
        model = await self._model(return_id, customer_id, expected_version)
        if model is None:
            return None
        model.status = status
        timestamps = {
            ReturnStatus.APPROVED: "approved_at",
            ReturnStatus.RECEIVED: "received_at",
            ReturnStatus.INSPECTED: "inspected_at",
            ReturnStatus.REJECTED: "rejected_at",
            ReturnStatus.CANCELLED: "cancelled_at",
        }
        field = timestamps.get(status)
        if field is not None:
            setattr(model, field, transitioned_at)
        if archive:
            model.deleted_at = transitioned_at
            model.deleted_by_id = actor_id
        model.updated_by_id = actor_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _return(model)

    async def _model(
        self, return_id: UUID, customer_id: UUID, version: int | None = None
    ) -> ReturnModel | None:
        query = select(ReturnModel).where(
            ReturnModel.id == return_id,
            ReturnModel.customer_id == customer_id,
            ReturnModel.deleted_at.is_(None),
        )
        if version is not None:
            query = query.where(ReturnModel.version == version)
        model: ReturnModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyReturnItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(
        self, values: Sequence[Mapping[str, object]]
    ) -> Sequence[ReturnItem]:
        models = [ReturnItemModel(**dict(value)) for value in values]
        self._session.add_all(models)
        await self._session.flush()
        for model in models:
            await self._session.refresh(model)
        return [_item(model) for model in models]

    async def list_for_return(self, return_id: UUID) -> Sequence[ReturnItem]:
        rows = (
            await self._session.scalars(
                select(ReturnItemModel)
                .where(ReturnItemModel.return_id == return_id)
                .order_by(ReturnItemModel.created_at, ReturnItemModel.id)
            )
        ).all()
        return [_item(row) for row in rows]

    async def committed_quantity(self, order_item_id: UUID) -> int:
        value = await self._session.scalar(
            select(func.coalesce(func.sum(ReturnItemModel.quantity), 0))
            .join(ReturnModel)
            .where(
                ReturnItemModel.order_item_id == order_item_id,
                ReturnModel.status.notin_(
                    {ReturnStatus.REJECTED, ReturnStatus.CANCELLED}
                ),
                ReturnModel.deleted_at.is_(None),
            )
        )
        return int(value or 0)

    async def inspect(
        self,
        return_id: UUID,
        dispositions: Mapping[UUID, InventoryDisposition],
        inspected_at: datetime,
    ) -> Sequence[ReturnItem]:
        models = (
            await self._session.scalars(
                select(ReturnItemModel).where(ReturnItemModel.return_id == return_id)
            )
        ).all()
        if {model.id for model in models} != set(dispositions):
            return ()
        for model in models:
            model.disposition = dispositions[model.id]
            model.inspected_at = inspected_at
        await self._session.flush()
        return [_item(model) for model in models]


class SqlAlchemyRefundRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, values: Mapping[str, object]) -> Refund:
        model = RefundModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _refund(model)

    async def get_for_return(self, return_id: UUID) -> Refund | None:
        model = await self._session.scalar(
            select(RefundModel).where(RefundModel.return_id == return_id)
        )
        return _refund(model) if model else None

    async def get_for_customer(
        self, refund_id: UUID, customer_id: UUID
    ) -> Refund | None:
        model = await self._model(refund_id, customer_id)
        return _refund(model) if model else None

    async def list_for_customer(
        self, customer_id: UUID, filters: RefundFilter
    ) -> tuple[Sequence[Refund], int]:
        query = select(RefundModel).where(
            RefundModel.customer_id == customer_id, RefundModel.deleted_at.is_(None)
        )
        if filters.return_id is not None:
            query = query.where(RefundModel.return_id == filters.return_id)
        if filters.status is not None:
            query = query.where(RefundModel.status == filters.status)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(RefundModel.created_at.desc(), RefundModel.id)
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_refund(row) for row in rows], total

    async def completed_amount(self, payment_id: UUID) -> Decimal:
        value = await self._session.scalar(
            select(func.coalesce(func.sum(RefundModel.amount), 0)).where(
                RefundModel.payment_id == payment_id,
                RefundModel.status == RefundStatus.COMPLETED,
            )
        )
        return Decimal(value or 0)

    async def transition(
        self,
        refund_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: RefundStatus,
        provider_reference: str | None,
        transitioned_at: datetime,
        actor_id: UUID,
    ) -> Refund | None:
        model = await self._model(refund_id, customer_id, expected_version)
        if model is None:
            return None
        model.status = status
        if provider_reference is not None:
            model.provider_reference = provider_reference
        if status is RefundStatus.COMPLETED:
            model.completed_at = transitioned_at
        elif status is RefundStatus.FAILED:
            model.failed_at = transitioned_at
        model.updated_by_id = actor_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _refund(model)

    async def _model(
        self, refund_id: UUID, customer_id: UUID, version: int | None = None
    ) -> RefundModel | None:
        query = select(RefundModel).where(
            RefundModel.id == refund_id,
            RefundModel.customer_id == customer_id,
            RefundModel.deleted_at.is_(None),
        )
        if version is not None:
            query = query.where(RefundModel.version == version)
        model: RefundModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyRefundTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, values: Mapping[str, object]) -> RefundTransaction:
        model = RefundTransactionModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _transaction(model)

    async def list_for_refund(self, refund_id: UUID) -> Sequence[RefundTransaction]:
        rows = (
            await self._session.scalars(
                select(RefundTransactionModel)
                .where(RefundTransactionModel.refund_id == refund_id)
                .order_by(RefundTransactionModel.occurred_at, RefundTransactionModel.id)
            )
        ).all()
        return [_transaction(row) for row in rows]


class SqlAlchemyReturnOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: ReturnEvent | RefundEvent) -> None:
        if isinstance(event, ReturnEvent):
            aggregate_type, aggregate_id = "return", event.return_id
        else:
            aggregate_type, aggregate_id = "refund", event.refund_id
        self._session.add(
            EventOutboxModel(
                id=event.event_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_name=event.event_name,
                payload=cast(dict[str, object], event.payload),
                occurred_at=event.occurred_at,
                status=OutboxStatus.PENDING,
            )
        )
        await self._session.flush()


def _return(model: ReturnModel) -> ProductReturn:
    return ProductReturn(
        id=model.id,
        order_id=model.order_id,
        shipment_id=model.shipment_id,
        payment_id=model.payment_id,
        customer_id=model.customer_id,
        store_id=model.store_id,
        status=model.status,
        reason=model.reason,
        requested_at=model.requested_at,
        approved_at=model.approved_at,
        received_at=model.received_at,
        inspected_at=model.inspected_at,
        rejected_at=model.rejected_at,
        cancelled_at=model.cancelled_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _item(model: ReturnItemModel) -> ReturnItem:
    return ReturnItem(
        id=model.id,
        return_id=model.return_id,
        order_item_id=model.order_item_id,
        variant_id=model.variant_id,
        inventory_item_id=model.inventory_item_id,
        quantity=model.quantity,
        unit_price=model.unit_price,
        currency=model.currency,
        disposition=model.disposition,
        inspected_at=model.inspected_at,
        created_at=model.created_at,
    )


def _refund(model: RefundModel) -> Refund:
    return Refund(
        id=model.id,
        return_id=model.return_id,
        payment_id=model.payment_id,
        customer_id=model.customer_id,
        store_id=model.store_id,
        status=model.status,
        amount=model.amount,
        currency=model.currency,
        provider=model.provider,
        provider_reference=model.provider_reference,
        completed_at=model.completed_at,
        failed_at=model.failed_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _transaction(model: RefundTransactionModel) -> RefundTransaction:
    return RefundTransaction(
        id=model.id,
        refund_id=model.refund_id,
        provider_transaction_id=model.provider_transaction_id,
        event_type=model.event_type,
        status=model.status,
        provider_payload=cast(dict[str, JsonValue], model.provider_payload),
        occurred_at=model.occurred_at,
        created_at=model.created_at,
    )
