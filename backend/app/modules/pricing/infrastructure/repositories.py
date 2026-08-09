from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalogs.infrastructure.models import CatalogModel
from app.modules.pricing.application.schemas import ProductPriceFilter
from app.modules.pricing.domain import PriceStatus, ProductPrice
from app.modules.pricing.infrastructure.models import ProductPriceModel
from app.modules.products.infrastructure.models import ProductModel
from app.modules.products.infrastructure.variant_models import ProductVariantModel
from app.modules.stores.infrastructure.persistence.access import store_accessible_by
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyProductPriceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store_owned(self, store_id: UUID, owner_id: UUID) -> bool:
        return (
            await self._session.scalar(
                select(StoreModel.id).where(
                    StoreModel.id == store_id,
                    store_accessible_by(owner_id),
                    StoreModel.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def product_context(
        self, product_id: UUID, owner_id: UUID
    ) -> Mapping[str, object] | None:
        row = (
            await self._session.execute(
                select(ProductModel.store_id, ProductModel.catalog_id)
                .join(StoreModel, StoreModel.id == ProductModel.store_id)
                .where(
                    ProductModel.id == product_id,
                    ProductModel.deleted_at.is_(None),
                    store_accessible_by(owner_id),
                    StoreModel.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return {"store_id": row.store_id, "catalog_id": row.catalog_id}

    async def catalog_owned(
        self, catalog_id: UUID, store_id: UUID, owner_id: UUID
    ) -> bool:
        return (
            await self._session.scalar(
                select(CatalogModel.id)
                .join(StoreModel, StoreModel.id == CatalogModel.store_id)
                .where(
                    CatalogModel.id == catalog_id,
                    CatalogModel.store_id == store_id,
                    CatalogModel.deleted_at.is_(None),
                    store_accessible_by(owner_id),
                    StoreModel.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def variant_owned(
        self, variant_id: UUID, product_id: UUID, store_id: UUID, owner_id: UUID
    ) -> bool:
        return (
            await self._session.scalar(
                select(ProductVariantModel.id)
                .join(StoreModel, StoreModel.id == ProductVariantModel.store_id)
                .where(
                    ProductVariantModel.id == variant_id,
                    ProductVariantModel.product_id == product_id,
                    ProductVariantModel.store_id == store_id,
                    ProductVariantModel.deleted_at.is_(None),
                    ProductVariantModel.is_active.is_(True),
                    store_accessible_by(owner_id),
                    StoreModel.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def active_price_exists(
        self,
        *,
        product_id: UUID,
        variant_id: UUID | None,
        currency_code: str,
        effective_from: datetime | None,
        effective_until: datetime | None,
        exclude_id: UUID | None = None,
    ) -> bool:
        query = select(ProductPriceModel.id).where(
            ProductPriceModel.product_id == product_id,
            ProductPriceModel.currency_code == currency_code,
            ProductPriceModel.status == PriceStatus.ACTIVE,
            ProductPriceModel.deleted_at.is_(None),
        )
        query = query.where(
            (
                ProductPriceModel.variant_id.is_(None)
                if variant_id is None
                else ProductPriceModel.variant_id == variant_id
            ),
            (
                ProductPriceModel.effective_from.is_(None)
                if effective_from is None
                else ProductPriceModel.effective_from == effective_from
            ),
            (
                ProductPriceModel.effective_until.is_(None)
                if effective_until is None
                else ProductPriceModel.effective_until == effective_until
            ),
        )
        if exclude_id is not None:
            query = query.where(ProductPriceModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def add(self, values: Mapping[str, object]) -> ProductPrice:
        persisted = dict(values)
        actor_id = persisted.pop("actor_id", None)
        model = ProductPriceModel(
            **persisted,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def list_for_owner(
        self, owner_id: UUID, filters: ProductPriceFilter
    ) -> tuple[Sequence[ProductPrice], int]:
        query = (
            select(ProductPriceModel)
            .join(StoreModel, StoreModel.id == ProductPriceModel.store_id)
            .where(
                store_accessible_by(owner_id),
                StoreModel.deleted_at.is_(None),
                ProductPriceModel.deleted_at.is_(None),
            )
        )
        for field, value in (
            ("store_id", filters.store_id),
            ("product_id", filters.product_id),
            ("variant_id", filters.variant_id),
            ("currency_code", filters.currency),
            ("status", filters.status),
        ):
            if value is not None:
                query = query.where(getattr(ProductPriceModel, field) == value)
        if filters.effective_at is not None:
            query = query.where(
                (ProductPriceModel.effective_from.is_(None))
                | (ProductPriceModel.effective_from <= filters.effective_at),
                (ProductPriceModel.effective_until.is_(None))
                | (ProductPriceModel.effective_until > filters.effective_at),
            )
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        models = (
            await self._session.scalars(
                query.order_by(
                    ProductPriceModel.updated_at.desc(), ProductPriceModel.id
                )
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_to_domain(model) for model in models], total

    async def get_for_owner(
        self, price_id: UUID, owner_id: UUID
    ) -> ProductPrice | None:
        model = await self._session.scalar(
            select(ProductPriceModel)
            .join(StoreModel, StoreModel.id == ProductPriceModel.store_id)
            .where(
                ProductPriceModel.id == price_id,
                ProductPriceModel.deleted_at.is_(None),
                store_accessible_by(owner_id),
                StoreModel.deleted_at.is_(None),
            )
        )
        return _to_domain(model) if model else None

    async def update(
        self,
        price_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> ProductPrice | None:
        model = await self._versioned_model(price_id, owner_id, expected_version)
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
        price_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> ProductPrice | None:
        model = await self._versioned_model(price_id, owner_id, expected_version)
        if model is None:
            return None
        model.status = PriceStatus.ARCHIVED
        model.deleted_at = deleted_at
        model.deleted_by_id = deleted_by_id
        model.updated_by_id = deleted_by_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def transition(
        self,
        price_id: UUID,
        owner_id: UUID,
        *,
        status: PriceStatus,
        expected_version: int,
        updated_by_id: UUID,
    ) -> ProductPrice | None:
        return await self.update(
            price_id,
            owner_id,
            values={"status": status, "updated_by_id": updated_by_id},
            expected_version=expected_version,
        )

    async def _versioned_model(
        self, price_id: UUID, owner_id: UUID, expected_version: int
    ) -> ProductPriceModel | None:
        model: ProductPriceModel | None = await self._session.scalar(
            select(ProductPriceModel)
            .join(StoreModel, StoreModel.id == ProductPriceModel.store_id)
            .where(
                ProductPriceModel.id == price_id,
                ProductPriceModel.deleted_at.is_(None),
                ProductPriceModel.version == expected_version,
                store_accessible_by(owner_id),
                StoreModel.deleted_at.is_(None),
            )
        )
        return model


def _to_domain(model: ProductPriceModel) -> ProductPrice:
    return ProductPrice(
        id=model.id,
        store_id=model.store_id,
        product_id=model.product_id,
        variant_id=model.variant_id,
        currency_code=model.currency_code,
        base_price=model.base_price,
        sale_price=model.sale_price,
        compare_at_price=model.compare_at_price,
        cost_price=model.cost_price,
        tax_class=model.tax_class,
        status=model.status,
        effective_from=model.effective_from,
        effective_until=model.effective_until,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )
