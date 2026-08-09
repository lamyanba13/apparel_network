from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalogs.domain.taxonomy import Category, Collection
from app.modules.catalogs.infrastructure.taxonomy_models import (
    CategoryModel,
    CollectionModel,
    CollectionProductModel,
    ProductCategoryModel,
)
from app.modules.products.infrastructure.models import ProductModel
from app.modules.stores.infrastructure.persistence.access import store_accessible_by
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyTaxonomyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def store_owned(self, store_id: UUID, owner_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(StoreModel.id).where(
                    StoreModel.id == store_id,
                    store_accessible_by(owner_id),
                    StoreModel.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def category_in_store(self, category_id: UUID, store_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(CategoryModel.id).where(
                    CategoryModel.id == category_id,
                    CategoryModel.store_id == store_id,
                    CategoryModel.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def parent_id(self, category_id: UUID) -> UUID | None:
        return await self.session.scalar(
            select(CategoryModel.parent_category_id).where(
                CategoryModel.id == category_id
            )
        )

    async def slug_exists(
        self, store_id: UUID, slug: str, exclude_id: UUID | None = None
    ) -> bool:
        criteria = [
            CategoryModel.store_id == store_id,
            CategoryModel.slug == slug,
            CategoryModel.deleted_at.is_(None),
        ]
        if exclude_id is not None:
            criteria.append(CategoryModel.id != exclude_id)
        return (
            await self.session.scalar(select(CategoryModel.id).where(*criteria))
            is not None
        )

    async def collection_slug_exists(
        self, store_id: UUID, slug: str, exclude_id: UUID | None = None
    ) -> bool:
        criteria = [
            CollectionModel.store_id == store_id,
            CollectionModel.slug == slug,
            CollectionModel.deleted_at.is_(None),
        ]
        if exclude_id is not None:
            criteria.append(CollectionModel.id != exclude_id)
        return (
            await self.session.scalar(select(CollectionModel.id).where(*criteria))
            is not None
        )

    async def add_category(self, values: Mapping[str, Any], owner_id: UUID) -> Category:
        model = CategoryModel(**dict(values), created_by_id=owner_id)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return category_domain(model)

    async def add_collection(
        self, values: Mapping[str, Any], owner_id: UUID
    ) -> Collection:
        model = CollectionModel(**dict(values), created_by_id=owner_id)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return collection_domain(model)

    async def list_categories(self, owner_id: UUID) -> Sequence[Category]:
        rows = (
            await self.session.scalars(
                select(CategoryModel)
                .join(StoreModel)
                .where(
                    store_accessible_by(owner_id), CategoryModel.deleted_at.is_(None)
                )
                .order_by(CategoryModel.sort_order, CategoryModel.name)
            )
        ).all()
        return [category_domain(row) for row in rows]

    async def list_collections(self, owner_id: UUID) -> Sequence[Collection]:
        rows = (
            await self.session.scalars(
                select(CollectionModel)
                .join(StoreModel)
                .where(
                    store_accessible_by(owner_id),
                    CollectionModel.deleted_at.is_(None),
                )
                .order_by(CollectionModel.sort_order, CollectionModel.name)
            )
        ).all()
        return [collection_domain(row) for row in rows]

    async def get_category(self, entity_id: UUID, owner_id: UUID) -> Category | None:
        model = await self.session.scalar(
            select(CategoryModel)
            .join(StoreModel)
            .where(
                CategoryModel.id == entity_id,
                store_accessible_by(owner_id),
                CategoryModel.deleted_at.is_(None),
            )
        )
        return category_domain(model) if model else None

    async def get_collection(
        self, entity_id: UUID, owner_id: UUID
    ) -> Collection | None:
        model = await self.session.scalar(
            select(CollectionModel)
            .join(StoreModel)
            .where(
                CollectionModel.id == entity_id,
                store_accessible_by(owner_id),
                CollectionModel.deleted_at.is_(None),
            )
        )
        return collection_domain(model) if model else None

    async def update_category(
        self, entity_id: UUID, owner_id: UUID, values: Mapping[str, Any], version: int
    ) -> Category | None:
        model = await self.session.scalar(
            select(CategoryModel)
            .join(StoreModel)
            .where(
                CategoryModel.id == entity_id,
                store_accessible_by(owner_id),
                CategoryModel.version == version,
                CategoryModel.deleted_at.is_(None),
            )
        )
        return await self._update(model, values, owner_id, category_domain)  # type: ignore[no-any-return]

    async def update_collection(
        self, entity_id: UUID, owner_id: UUID, values: Mapping[str, Any], version: int
    ) -> Collection | None:
        model = await self.session.scalar(
            select(CollectionModel)
            .join(StoreModel)
            .where(
                CollectionModel.id == entity_id,
                store_accessible_by(owner_id),
                CollectionModel.version == version,
                CollectionModel.deleted_at.is_(None),
            )
        )
        return await self._update(model, values, owner_id, collection_domain)  # type: ignore[no-any-return]

    async def _update(
        self, model: Any, values: Mapping[str, Any], owner_id: UUID, mapper: Any
    ) -> Any:
        if model is None:
            return None
        for key, value in values.items():
            setattr(model, key, value)
        model.updated_by_id = owner_id
        model.version += 1
        await self.session.flush()
        await self.session.refresh(model)
        return mapper(model)

    async def archive_category(
        self, entity_id: UUID, owner_id: UUID, version: int
    ) -> Category | None:
        return await self._archive(  # type: ignore[no-any-return]
            entity_id, owner_id, version, CategoryModel, category_domain
        )

    async def archive_collection(
        self, entity_id: UUID, owner_id: UUID, version: int
    ) -> Collection | None:
        return await self._archive(  # type: ignore[no-any-return]
            entity_id, owner_id, version, CollectionModel, collection_domain
        )

    async def _archive(
        self,
        entity_id: UUID,
        owner_id: UUID,
        version: int,
        model_type: Any,
        mapper: Any,
    ) -> Any:
        model = await self.session.scalar(
            select(model_type)
            .join(StoreModel)
            .where(
                model_type.id == entity_id,
                store_accessible_by(owner_id),
                model_type.version == version,
                model_type.deleted_at.is_(None),
            )
        )
        if model is None:
            return None
        model.status = "archived"
        model.deleted_at = datetime.now(UTC)
        model.updated_by_id = owner_id
        model.version += 1
        await self.session.flush()
        await self.session.refresh(model)
        return mapper(model)

    async def product_in_store(self, product_id: UUID, store_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(ProductModel.id).where(
                    ProductModel.id == product_id,
                    ProductModel.store_id == store_id,
                    ProductModel.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def assign_category(self, category_id: UUID, product_id: UUID) -> None:
        self.session.add(
            ProductCategoryModel(category_id=category_id, product_id=product_id)
        )
        await self.session.flush()

    async def remove_category(self, category_id: UUID, product_id: UUID) -> None:
        await self.session.execute(
            delete(ProductCategoryModel).where(
                ProductCategoryModel.category_id == category_id,
                ProductCategoryModel.product_id == product_id,
            )
        )
        await self.session.flush()

    async def assign_collection(self, collection_id: UUID, product_id: UUID) -> None:
        self.session.add(
            CollectionProductModel(collection_id=collection_id, product_id=product_id)
        )
        await self.session.flush()

    async def remove_collection(self, collection_id: UUID, product_id: UUID) -> None:
        await self.session.execute(
            delete(CollectionProductModel).where(
                CollectionProductModel.collection_id == collection_id,
                CollectionProductModel.product_id == product_id,
            )
        )
        await self.session.flush()

    async def reorder_collection(
        self, entity_id: UUID, owner_id: UUID, product_ids: Sequence[UUID], version: int
    ) -> Collection | None:
        value = await self.get_collection(entity_id, owner_id)
        if value is None or value.version != version:
            return None
        for index, product_id in enumerate(product_ids):
            await self.session.execute(
                update(CollectionProductModel)
                .where(
                    CollectionProductModel.collection_id == entity_id,
                    CollectionProductModel.product_id == product_id,
                )
                .values(display_order=index)
            )
        return await self.update_collection(entity_id, owner_id, {}, version)


def category_domain(model: CategoryModel) -> Category:
    return Category(
        model.id,
        model.store_id,
        model.name,
        model.slug,
        model.description,
        model.parent_category_id,
        model.sort_order,
        model.status,
        model.visibility,
        model.created_at,
        model.updated_at,
        model.deleted_at,
        model.version,
        model.created_by_id,
        model.updated_by_id,
    )


def collection_domain(model: CollectionModel) -> Collection:
    return Collection(
        model.id,
        model.store_id,
        model.name,
        model.slug,
        model.description,
        model.sort_order,
        model.status,
        model.visibility,
        model.collection_type,
        model.created_at,
        model.updated_at,
        model.deleted_at,
        model.version,
        model.created_by_id,
        model.updated_by_id,
    )
