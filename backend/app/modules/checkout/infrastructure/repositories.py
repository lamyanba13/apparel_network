from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkout.application.schemas import CheckoutFilter
from app.modules.checkout.domain import (
    CheckoutEvent,
    CheckoutItem,
    CheckoutSession,
    CheckoutStatus,
)
from app.modules.checkout.infrastructure.models import (
    CheckoutSessionItemModel,
    CheckoutSessionModel,
)
from app.modules.inventory.domain import InventoryStatus
from app.modules.inventory.infrastructure.models import InventoryItemModel
from app.modules.products.domain import OutboxStatus
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.products.infrastructure.models import ProductModel
from app.modules.products.infrastructure.variant_models import ProductVariantModel
from app.modules.stores.domain import StoreStatus, VerificationStatus
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyCheckoutRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists_for_cart(self, cart_id: UUID) -> bool:
        return (
            await self._session.scalar(
                select(CheckoutSessionModel.id).where(
                    CheckoutSessionModel.cart_id == cart_id
                )
            )
            is not None
        )

    async def add(self, values: Mapping[str, object]) -> CheckoutSession:
        model = CheckoutSessionModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _checkout(model)

    async def list_for_user(
        self, user_id: UUID, filters: CheckoutFilter
    ) -> tuple[Sequence[CheckoutSession], int]:
        query = select(CheckoutSessionModel).where(
            CheckoutSessionModel.user_id == user_id,
            CheckoutSessionModel.deleted_at.is_(None),
        )
        if filters.status is not None:
            query = query.where(CheckoutSessionModel.status == filters.status)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(
                    CheckoutSessionModel.updated_at.desc(), CheckoutSessionModel.id
                )
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_checkout(row) for row in rows], total

    async def get_for_user(
        self, checkout_id: UUID, user_id: UUID
    ) -> CheckoutSession | None:
        model = await self._model(checkout_id, user_id)
        return _checkout(model) if model else None

    async def transition(
        self,
        checkout_id: UUID,
        user_id: UUID,
        *,
        expected_version: int,
        status: CheckoutStatus,
        transitioned_at: datetime,
        actor_id: UUID,
    ) -> CheckoutSession | None:
        model = await self._model(checkout_id, user_id, expected_version)
        if model is None or model.status is not CheckoutStatus.ACTIVE:
            return None
        model.status = status
        model.completed_at = (
            transitioned_at if status is CheckoutStatus.CONFIRMED else None
        )
        model.updated_by_id = actor_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _checkout(model)

    async def archive(
        self,
        checkout_id: UUID,
        user_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> CheckoutSession | None:
        model = await self._model(checkout_id, user_id, expected_version)
        if model is None or model.status is not CheckoutStatus.ACTIVE:
            return None
        model.status = CheckoutStatus.CANCELLED
        model.deleted_at = deleted_at
        model.deleted_by_id = deleted_by_id
        model.updated_by_id = deleted_by_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _checkout(model)

    async def _model(
        self, checkout_id: UUID, user_id: UUID, version: int | None = None
    ) -> CheckoutSessionModel | None:
        query = select(CheckoutSessionModel).where(
            CheckoutSessionModel.id == checkout_id,
            CheckoutSessionModel.user_id == user_id,
            CheckoutSessionModel.deleted_at.is_(None),
        )
        if version is not None:
            query = query.where(CheckoutSessionModel.version == version)
        model: CheckoutSessionModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyCheckoutItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(
        self, values: Sequence[Mapping[str, object]]
    ) -> Sequence[CheckoutItem]:
        models = [CheckoutSessionItemModel(**dict(value)) for value in values]
        self._session.add_all(models)
        await self._session.flush()
        for model in models:
            await self._session.refresh(model)
        return [_item(model) for model in models]

    async def list_for_checkout(self, checkout_id: UUID) -> Sequence[CheckoutItem]:
        rows = (
            await self._session.scalars(
                select(CheckoutSessionItemModel)
                .where(CheckoutSessionItemModel.checkout_session_id == checkout_id)
                .order_by(
                    CheckoutSessionItemModel.created_at, CheckoutSessionItemModel.id
                )
            )
        ).all()
        return [_item(row) for row in rows]

    async def validation_context(
        self, variant_id: UUID, store_id: UUID
    ) -> Mapping[str, object] | None:
        row = (
            await self._session.execute(
                select(
                    ProductVariantModel.product_id,
                    StoreModel.owner_id.label("store_owner_id"),
                    InventoryItemModel.id.label("inventory_id"),
                )
                .join(ProductModel, ProductModel.id == ProductVariantModel.product_id)
                .join(StoreModel, StoreModel.id == ProductVariantModel.store_id)
                .join(
                    InventoryItemModel,
                    InventoryItemModel.variant_id == ProductVariantModel.id,
                )
                .where(
                    ProductVariantModel.id == variant_id,
                    ProductVariantModel.store_id == store_id,
                    ProductVariantModel.is_active.is_(True),
                    ProductVariantModel.deleted_at.is_(None),
                    ProductModel.deleted_at.is_(None),
                    StoreModel.status == StoreStatus.ACTIVE,
                    StoreModel.verification_status == VerificationStatus.VERIFIED,
                    StoreModel.deleted_at.is_(None),
                    InventoryItemModel.status == InventoryStatus.ACTIVE,
                    InventoryItemModel.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return {
            "product_id": row.product_id,
            "store_owner_id": row.store_owner_id,
            "inventory_id": row.inventory_id,
        }


class SqlAlchemyCheckoutOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: CheckoutEvent) -> None:
        self._session.add(
            EventOutboxModel(
                id=event.event_id,
                aggregate_type="checkout_session",
                aggregate_id=event.checkout_id,
                event_name=event.event_name,
                payload=cast(dict[str, object], event.payload),
                occurred_at=event.occurred_at,
                status=OutboxStatus.PENDING,
            )
        )
        await self._session.flush()


def _checkout(model: CheckoutSessionModel) -> CheckoutSession:
    return CheckoutSession(
        id=model.id,
        cart_id=model.cart_id,
        user_id=model.user_id,
        store_id=model.store_id,
        status=model.status,
        currency=model.currency,
        subtotal=model.subtotal,
        expires_at=model.expires_at,
        completed_at=model.completed_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _item(model: CheckoutSessionItemModel) -> CheckoutItem:
    return CheckoutItem(
        id=model.id,
        checkout_session_id=model.checkout_session_id,
        product_id=model.product_id,
        variant_id=model.variant_id,
        quantity=model.quantity,
        price_id=model.price_id,
        unit_price=model.unit_price,
        currency=model.currency,
        inventory_id=model.inventory_id,
        inventory_version=model.inventory_version,
        price_snapshot_time=model.price_snapshot_time,
        inventory_snapshot_time=model.inventory_snapshot_time,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
    )
