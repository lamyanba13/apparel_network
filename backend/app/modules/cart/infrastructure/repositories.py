from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cart.application.schemas import CartFilter
from app.modules.cart.domain import (
    CartEvent,
    CartStatus,
    ShoppingCart,
    ShoppingCartItem,
)
from app.modules.cart.infrastructure.models import (
    ShoppingCartItemModel,
    ShoppingCartModel,
)
from app.modules.inventory.domain import InventoryStatus
from app.modules.inventory.infrastructure.models import InventoryItemModel
from app.modules.products.domain import OutboxStatus
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.products.infrastructure.models import ProductModel
from app.modules.products.infrastructure.variant_models import ProductVariantModel
from app.modules.stores.domain import StoreStatus, VerificationStatus
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyShoppingCartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store_exists(self, store_id: UUID) -> bool:
        return (
            await self._session.scalar(
                select(StoreModel.id).where(
                    StoreModel.id == store_id,
                    StoreModel.status == StoreStatus.ACTIVE,
                    StoreModel.verification_status == VerificationStatus.VERIFIED,
                    StoreModel.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def active_exists(self, user_id: UUID, store_id: UUID) -> bool:
        return (
            await self._session.scalar(
                select(ShoppingCartModel.id).where(
                    ShoppingCartModel.user_id == user_id,
                    ShoppingCartModel.store_id == store_id,
                    ShoppingCartModel.status == CartStatus.ACTIVE,
                    ShoppingCartModel.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def add(self, values: Mapping[str, object]) -> ShoppingCart:
        model = ShoppingCartModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _cart(model)

    async def list_for_user(
        self, user_id: UUID, filters: CartFilter
    ) -> tuple[Sequence[ShoppingCart], int]:
        query = select(ShoppingCartModel).where(
            ShoppingCartModel.user_id == user_id,
            ShoppingCartModel.deleted_at.is_(None),
        )
        if filters.store_id is not None:
            query = query.where(ShoppingCartModel.store_id == filters.store_id)
        if filters.status is not None:
            query = query.where(ShoppingCartModel.status == filters.status)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(
                    ShoppingCartModel.updated_at.desc(), ShoppingCartModel.id
                )
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_cart(row) for row in rows], total

    async def get_for_user(self, cart_id: UUID, user_id: UUID) -> ShoppingCart | None:
        model = await self._model(cart_id, user_id)
        return _cart(model) if model else None

    async def touch(
        self,
        cart_id: UUID,
        user_id: UUID,
        *,
        expected_version: int,
        updated_by_id: UUID,
    ) -> ShoppingCart | None:
        model = await self._model(cart_id, user_id, expected_version)
        if model is None or model.status is not CartStatus.ACTIVE:
            return None
        model.updated_by_id = updated_by_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _cart(model)

    async def transition(
        self,
        cart_id: UUID,
        user_id: UUID,
        *,
        expected_version: int,
        status: CartStatus,
        transitioned_at: datetime,
        actor_id: UUID,
    ) -> ShoppingCart | None:
        model = await self._model(cart_id, user_id, expected_version)
        if model is None or model.status is not CartStatus.ACTIVE:
            return None
        model.status = status
        model.checked_out_at = (
            transitioned_at if status is CartStatus.CHECKED_OUT else None
        )
        model.updated_by_id = actor_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _cart(model)

    async def archive(
        self,
        cart_id: UUID,
        user_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> ShoppingCart | None:
        model = await self._model(cart_id, user_id, expected_version)
        if model is None or model.status is not CartStatus.ACTIVE:
            return None
        model.status = CartStatus.ABANDONED
        model.deleted_at = deleted_at
        model.deleted_by_id = deleted_by_id
        model.updated_by_id = deleted_by_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _cart(model)

    async def _model(
        self, cart_id: UUID, user_id: UUID, version: int | None = None
    ) -> ShoppingCartModel | None:
        query = select(ShoppingCartModel).where(
            ShoppingCartModel.id == cart_id,
            ShoppingCartModel.user_id == user_id,
            ShoppingCartModel.deleted_at.is_(None),
        )
        if version is not None:
            query = query.where(ShoppingCartModel.version == version)
        model: ShoppingCartModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyShoppingCartItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def variant_context(
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

    async def add(self, values: Mapping[str, object]) -> ShoppingCartItem:
        model = ShoppingCartItemModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _item(model)

    async def list_for_cart(self, cart_id: UUID) -> Sequence[ShoppingCartItem]:
        rows = (
            await self._session.scalars(
                select(ShoppingCartItemModel)
                .where(
                    ShoppingCartItemModel.cart_id == cart_id,
                    ShoppingCartItemModel.deleted_at.is_(None),
                )
                .order_by(ShoppingCartItemModel.added_at, ShoppingCartItemModel.id)
            )
        ).all()
        return [_item(row) for row in rows]

    async def get_for_cart(
        self, item_id: UUID, cart_id: UUID
    ) -> ShoppingCartItem | None:
        model = await self._model(item_id, cart_id)
        return _item(model) if model else None

    async def get_by_variant(
        self, cart_id: UUID, variant_id: UUID
    ) -> ShoppingCartItem | None:
        model = await self._session.scalar(
            select(ShoppingCartItemModel).where(
                ShoppingCartItemModel.cart_id == cart_id,
                ShoppingCartItemModel.variant_id == variant_id,
                ShoppingCartItemModel.deleted_at.is_(None),
            )
        )
        return _item(model) if model else None

    async def update(
        self,
        item_id: UUID,
        cart_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> ShoppingCartItem | None:
        model = await self._model(item_id, cart_id, expected_version)
        if model is None:
            return None
        for key, value in values.items():
            setattr(model, key, value)
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _item(model)

    async def archive(
        self,
        item_id: UUID,
        cart_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> ShoppingCartItem | None:
        model = await self._model(item_id, cart_id, expected_version)
        if model is None:
            return None
        model.deleted_at = deleted_at
        model.deleted_by_id = deleted_by_id
        model.updated_by_id = deleted_by_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _item(model)

    async def archive_for_cart(
        self, cart_id: UUID, *, deleted_at: datetime, deleted_by_id: UUID
    ) -> None:
        await self._session.execute(
            update(ShoppingCartItemModel)
            .where(
                ShoppingCartItemModel.cart_id == cart_id,
                ShoppingCartItemModel.deleted_at.is_(None),
            )
            .values(
                deleted_at=deleted_at,
                deleted_by_id=deleted_by_id,
                updated_by_id=deleted_by_id,
                version=ShoppingCartItemModel.version + 1,
            )
        )
        await self._session.flush()

    async def _model(
        self, item_id: UUID, cart_id: UUID, version: int | None = None
    ) -> ShoppingCartItemModel | None:
        query = select(ShoppingCartItemModel).where(
            ShoppingCartItemModel.id == item_id,
            ShoppingCartItemModel.cart_id == cart_id,
            ShoppingCartItemModel.deleted_at.is_(None),
        )
        if version is not None:
            query = query.where(ShoppingCartItemModel.version == version)
        model: ShoppingCartItemModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyCartOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: CartEvent) -> None:
        self._session.add(
            EventOutboxModel(
                id=event.event_id,
                aggregate_type="shopping_cart",
                aggregate_id=event.cart_id,
                event_name=event.event_name,
                payload=cast(dict[str, object], event.payload),
                occurred_at=event.occurred_at,
                status=OutboxStatus.PENDING,
            )
        )
        await self._session.flush()


def _cart(model: ShoppingCartModel) -> ShoppingCart:
    return ShoppingCart(
        id=model.id,
        user_id=model.user_id,
        store_id=model.store_id,
        status=model.status,
        currency=model.currency,
        customer_group=model.customer_group,
        expires_at=model.expires_at,
        checked_out_at=model.checked_out_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _item(model: ShoppingCartItemModel) -> ShoppingCartItem:
    return ShoppingCartItem(
        id=model.id,
        cart_id=model.cart_id,
        product_id=model.product_id,
        variant_id=model.variant_id,
        quantity=model.quantity,
        price_snapshot_id=model.price_snapshot_id,
        unit_price=model.unit_price,
        currency=model.currency,
        inventory_snapshot=cast(dict[str, JsonValue], model.inventory_snapshot),
        added_at=model.added_at,
        updated_at=model.updated_at,
        version=model.version,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )
