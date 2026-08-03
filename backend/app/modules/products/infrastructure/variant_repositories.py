from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.products.domain.variants import ProductVariant
from app.modules.products.infrastructure.models import ProductModel
from app.modules.products.infrastructure.variant_models import ProductVariantModel
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyProductVariantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def product_store(self, product_id: UUID, owner_id: UUID) -> UUID | None:
        query = (
            select(ProductModel.store_id)
            .join(StoreModel)
            .where(
                ProductModel.id == product_id,
                ProductModel.deleted_at.is_(None),
                StoreModel.owner_id == owner_id,
            )
        )
        return cast(UUID | None, await self._session.scalar(query))

    async def add(self, values: Mapping[str, object]) -> ProductVariant:
        persisted = dict(values)
        actor_id = persisted.pop("actor_id", None)
        persisted["created_by_id"] = actor_id
        persisted["updated_by_id"] = actor_id
        model = ProductVariantModel(**persisted)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def list_for_product(
        self, product_id: UUID, owner_id: UUID
    ) -> Sequence[ProductVariant]:
        rows = (
            await self._session.scalars(
                select(ProductVariantModel)
                .join(StoreModel)
                .where(
                    ProductVariantModel.product_id == product_id,
                    ProductVariantModel.deleted_at.is_(None),
                    StoreModel.owner_id == owner_id,
                )
                .order_by(ProductVariantModel.sort_order, ProductVariantModel.reference)
            )
        ).all()
        return [_to_domain(row) for row in rows]

    async def get_for_owner(
        self, variant_id: UUID, product_id: UUID, owner_id: UUID
    ) -> ProductVariant | None:
        model = await self._session.scalar(
            select(ProductVariantModel)
            .join(StoreModel)
            .where(
                ProductVariantModel.id == variant_id,
                ProductVariantModel.product_id == product_id,
                ProductVariantModel.deleted_at.is_(None),
                StoreModel.owner_id == owner_id,
            )
        )
        return _to_domain(model) if model else None

    async def reference_exists(
        self, store_id: UUID, reference: str, *, exclude_id: UUID | None = None
    ) -> bool:
        query = select(ProductVariantModel.id).where(
            ProductVariantModel.store_id == store_id,
            ProductVariantModel.reference == reference,
            ProductVariantModel.deleted_at.is_(None),
        )
        if exclude_id is not None:
            query = query.where(ProductVariantModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def signature_exists(
        self, product_id: UUID, signature: str, *, exclude_id: UUID | None = None
    ) -> bool:
        query = select(ProductVariantModel.id).where(
            ProductVariantModel.product_id == product_id,
            ProductVariantModel.attribute_signature == signature,
            ProductVariantModel.deleted_at.is_(None),
        )
        if exclude_id is not None:
            query = query.where(ProductVariantModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def update(
        self,
        variant_id: UUID,
        product_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> ProductVariant | None:
        model = await self._session.scalar(
            select(ProductVariantModel)
            .join(StoreModel)
            .where(
                ProductVariantModel.id == variant_id,
                ProductVariantModel.product_id == product_id,
                ProductVariantModel.deleted_at.is_(None),
                ProductVariantModel.version == expected_version,
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

    async def archive(
        self,
        variant_id: UUID,
        product_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
    ) -> ProductVariant | None:
        model = await self._session.scalar(
            select(ProductVariantModel)
            .join(StoreModel)
            .where(
                ProductVariantModel.id == variant_id,
                ProductVariantModel.product_id == product_id,
                ProductVariantModel.deleted_at.is_(None),
                ProductVariantModel.version == expected_version,
                StoreModel.owner_id == owner_id,
            )
        )
        if model is None:
            return None
        model.deleted_at, model.is_active, model.updated_by_id = (
            deleted_at,
            False,
            owner_id,
        )
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)


def _to_domain(model: ProductVariantModel) -> ProductVariant:
    return ProductVariant(
        id=model.id,
        product_id=model.product_id,
        store_id=model.store_id,
        reference=model.reference,
        attributes=model.attributes,
        attribute_signature=model.attribute_signature,
        sort_order=model.sort_order,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        version=model.version,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
    )
