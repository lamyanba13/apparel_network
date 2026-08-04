from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.domain import InventoryItem, InventoryStatus
from app.modules.inventory.infrastructure.models import InventoryItemModel
from app.modules.products.infrastructure.models import ProductModel
from app.modules.products.infrastructure.variant_models import ProductVariantModel
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
                StoreModel.owner_id == owner_id,
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
                StoreModel.owner_id == owner_id, InventoryItemModel.deleted_at.is_(None)
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
                StoreModel.owner_id == owner_id,
            )
        )
        return _to_domain(model) if model else None

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
                StoreModel.owner_id == owner_id,
            )
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
                StoreModel.owner_id == owner_id,
            )
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
