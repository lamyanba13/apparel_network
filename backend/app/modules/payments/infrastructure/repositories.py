from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.application.schemas import PaymentFilter
from app.modules.payments.domain import (
    PaymentEvent,
    PaymentIntent,
    PaymentStatus,
    PaymentTransaction,
)
from app.modules.payments.infrastructure.models import (
    PaymentIntentModel,
    PaymentTransactionModel,
)
from app.modules.products.domain import OutboxStatus
from app.modules.products.infrastructure.attribute_models import EventOutboxModel


class SqlAlchemyPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_idempotency(
        self, customer_id: UUID, idempotency_key: str
    ) -> PaymentIntent | None:
        model = await self._session.scalar(
            select(PaymentIntentModel).where(
                PaymentIntentModel.customer_id == customer_id,
                PaymentIntentModel.idempotency_key == idempotency_key,
            )
        )
        return _payment(model) if model else None

    async def add(self, values: Mapping[str, object]) -> PaymentIntent:
        model = PaymentIntentModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _payment(model)

    async def list_for_customer(
        self, customer_id: UUID, filters: PaymentFilter
    ) -> tuple[Sequence[PaymentIntent], int]:
        query = select(PaymentIntentModel).where(
            PaymentIntentModel.customer_id == customer_id,
            PaymentIntentModel.deleted_at.is_(None),
        )
        if filters.store_id is not None:
            query = query.where(PaymentIntentModel.store_id == filters.store_id)
        if filters.order_id is not None:
            query = query.where(PaymentIntentModel.order_id == filters.order_id)
        if filters.status is not None:
            query = query.where(PaymentIntentModel.status == filters.status)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(
                    PaymentIntentModel.created_at.desc(), PaymentIntentModel.id
                )
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_payment(row) for row in rows], total

    async def get_for_customer(
        self, payment_id: UUID, customer_id: UUID
    ) -> PaymentIntent | None:
        model = await self._model(payment_id, customer_id)
        return _payment(model) if model else None

    async def transition(
        self,
        payment_id: UUID,
        customer_id: UUID,
        *,
        expected_version: int,
        status: PaymentStatus,
        transitioned_at: datetime,
        actor_id: UUID,
        archive: bool = False,
    ) -> PaymentIntent | None:
        model = await self._model(payment_id, customer_id, expected_version)
        if model is None:
            return None
        model.status = status
        if status is PaymentStatus.AUTHORIZED:
            model.authorized_at = transitioned_at
        elif status is PaymentStatus.CAPTURED:
            model.captured_at = transitioned_at
        elif status is PaymentStatus.FAILED:
            model.failed_at = transitioned_at
        elif status is PaymentStatus.CANCELLED:
            model.cancelled_at = transitioned_at
        if archive:
            model.deleted_at = transitioned_at
            model.deleted_by_id = actor_id
        model.updated_by_id = actor_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _payment(model)

    async def _model(
        self, payment_id: UUID, customer_id: UUID, version: int | None = None
    ) -> PaymentIntentModel | None:
        query = select(PaymentIntentModel).where(
            PaymentIntentModel.id == payment_id,
            PaymentIntentModel.customer_id == customer_id,
            PaymentIntentModel.deleted_at.is_(None),
        )
        if version is not None:
            query = query.where(PaymentIntentModel.version == version)
        model: PaymentIntentModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyPaymentTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, values: Mapping[str, object]) -> PaymentTransaction:
        model = PaymentTransactionModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _transaction(model)

    async def list_for_payment(self, payment_id: UUID) -> Sequence[PaymentTransaction]:
        rows = (
            await self._session.scalars(
                select(PaymentTransactionModel)
                .where(PaymentTransactionModel.payment_intent_id == payment_id)
                .order_by(
                    PaymentTransactionModel.occurred_at, PaymentTransactionModel.id
                )
            )
        ).all()
        return [_transaction(row) for row in rows]


class SqlAlchemyPaymentOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: PaymentEvent) -> None:
        self._session.add(
            EventOutboxModel(
                id=event.event_id,
                aggregate_type="payment",
                aggregate_id=event.payment_id,
                event_name=event.event_name,
                payload=cast(dict[str, object], event.payload),
                occurred_at=event.occurred_at,
                status=OutboxStatus.PENDING,
            )
        )
        await self._session.flush()


def _payment(model: PaymentIntentModel) -> PaymentIntent:
    return PaymentIntent(
        id=model.id,
        order_id=model.order_id,
        customer_id=model.customer_id,
        store_id=model.store_id,
        provider=model.provider,
        provider_reference=model.provider_reference,
        status=model.status,
        currency=model.currency,
        amount=model.amount,
        idempotency_key=model.idempotency_key,
        expires_at=model.expires_at,
        authorized_at=model.authorized_at,
        captured_at=model.captured_at,
        failed_at=model.failed_at,
        cancelled_at=model.cancelled_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _transaction(model: PaymentTransactionModel) -> PaymentTransaction:
    return PaymentTransaction(
        id=model.id,
        payment_intent_id=model.payment_intent_id,
        provider_transaction_id=model.provider_transaction_id,
        event_type=model.event_type,
        status=model.status,
        amount=model.amount,
        currency=model.currency,
        provider_payload=model.provider_payload,
        occurred_at=model.occurred_at,
        created_at=model.created_at,
    )
