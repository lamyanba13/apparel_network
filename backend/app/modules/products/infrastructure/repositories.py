from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalogs.domain import CatalogStatus
from app.modules.catalogs.infrastructure.models import CatalogModel
from app.modules.products.domain import Product, ProductStatus, ProductVisibility
from app.modules.products.infrastructure.models import ProductModel
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def catalog_store(self, catalog_id: UUID, owner_id: UUID) -> UUID | None:
        query = (
            select(CatalogModel.store_id)
            .join(StoreModel)
            .where(
                CatalogModel.id == catalog_id,
                StoreModel.owner_id == owner_id,
                CatalogModel.deleted_at.is_(None),
                CatalogModel.status != CatalogStatus.ARCHIVED,
            )
        )
        return cast(UUID | None, await self._session.scalar(query))

    async def add(self, values: Mapping[str, object]) -> Product:
        model = ProductModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def list_for_owner(
        self,
        owner_id: UUID,
        *,
        catalog_id: UUID | None,
        status: ProductStatus | None,
        visibility: ProductVisibility | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Product], int]:
        query = (
            select(ProductModel)
            .join(StoreModel, StoreModel.id == ProductModel.store_id)
            .where(StoreModel.owner_id == owner_id, ProductModel.deleted_at.is_(None))
        )
        if catalog_id is not None:
            query = query.where(ProductModel.catalog_id == catalog_id)
        if status is not None:
            query = query.where(ProductModel.status == status)
        if visibility is not None:
            query = query.where(ProductModel.visibility == visibility)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(ProductModel.sort_order, ProductModel.name)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [_to_domain(row) for row in rows], total

    async def get_for_owner(self, product_id: UUID, owner_id: UUID) -> Product | None:
        query = (
            select(ProductModel)
            .join(StoreModel, StoreModel.id == ProductModel.store_id)
            .where(
                ProductModel.id == product_id,
                StoreModel.owner_id == owner_id,
                ProductModel.deleted_at.is_(None),
            )
        )
        model = await self._session.scalar(query)
        return _to_domain(model) if model else None

    async def slug_exists(
        self, catalog_id: UUID, slug: str, *, exclude_id: UUID | None = None
    ) -> bool:
        query = select(ProductModel.id).where(
            ProductModel.catalog_id == catalog_id,
            ProductModel.slug == slug,
            ProductModel.deleted_at.is_(None),
        )
        if exclude_id is not None:
            query = query.where(ProductModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def sku_exists(
        self, store_id: UUID, sku: str, *, exclude_id: UUID | None = None
    ) -> bool:
        query = select(ProductModel.id).where(
            ProductModel.store_id == store_id,
            ProductModel.sku == sku,
            ProductModel.deleted_at.is_(None),
        )
        if exclude_id is not None:
            query = query.where(ProductModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def update(
        self,
        product_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> Product | None:
        model = await self._session.scalar(
            select(ProductModel)
            .join(StoreModel)
            .where(
                ProductModel.id == product_id,
                StoreModel.owner_id == owner_id,
                ProductModel.deleted_at.is_(None),
                ProductModel.version == expected_version,
            )
        )
        if model is None:
            return None
        for key, value in values.items():
            setattr(model, key, value)
        model.updated_by_id = owner_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def archive(
        self,
        product_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
    ) -> Product | None:
        model = await self._session.scalar(
            select(ProductModel)
            .join(StoreModel)
            .where(
                ProductModel.id == product_id,
                StoreModel.owner_id == owner_id,
                ProductModel.deleted_at.is_(None),
                ProductModel.version == expected_version,
            )
        )
        if model is None:
            return None
        model.status = ProductStatus.ARCHIVED
        model.deleted_at = deleted_at
        model.updated_by_id = owner_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def transition(
        self,
        product_id: UUID,
        owner_id: UUID,
        *,
        status: ProductStatus,
        expected_version: int,
    ) -> Product | None:
        model = await self._session.scalar(
            select(ProductModel)
            .join(StoreModel)
            .where(
                ProductModel.id == product_id,
                StoreModel.owner_id == owner_id,
                ProductModel.deleted_at.is_(None),
                ProductModel.version == expected_version,
            )
        )
        if model is None:
            return None
        model.status = status
        model.updated_by_id = owner_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)


def _to_domain(model: ProductModel) -> Product:
    return Product(
        id=model.id,
        catalog_id=model.catalog_id,
        store_id=model.store_id,
        name=model.name,
        slug=model.slug,
        short_description=model.short_description,
        description=model.description,
        status=model.status,
        visibility=model.visibility,
        sku=model.sku,
        brand=model.brand,
        sort_order=model.sort_order,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        version=model.version,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
    )
