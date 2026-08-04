from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.products.domain import AttributeStatus
from app.modules.products.domain.variants import ProductVariant
from app.modules.products.infrastructure.attribute_models import (
    ProductAttributeModel,
    ProductAttributeValueModel,
    ProductVariantAttributeValueModel,
)
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
        value_ids = cast(Sequence[UUID], persisted.pop("attribute_value_ids"))
        persisted["created_by_id"] = actor_id
        persisted["updated_by_id"] = actor_id
        model = ProductVariantModel(**persisted)
        self._session.add(model)
        await self._session.flush()
        self._session.add_all(
            ProductVariantAttributeValueModel(
                variant_id=model.id, attribute_value_id=value_id
            )
            for value_id in value_ids
        )
        await self._session.flush()
        await self._session.refresh(model)
        return await self._to_domain(model)

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
        return [await self._to_domain(row) for row in rows]

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
        return await self._to_domain(model) if model else None

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

    async def resolve_attribute_values(
        self, store_id: UUID, attributes: Mapping[str, str]
    ) -> Sequence[Mapping[str, object]] | None:
        resolved: list[Mapping[str, object]] = []
        for slug, requested_value in attributes.items():
            row = (
                await self._session.execute(
                    select(
                        ProductAttributeModel.id.label("attribute_id"),
                        ProductAttributeModel.slug.label("attribute_slug"),
                        ProductAttributeValueModel.id.label("value_id"),
                        ProductAttributeValueModel.value,
                    )
                    .join(
                        ProductAttributeValueModel,
                        ProductAttributeValueModel.attribute_id
                        == ProductAttributeModel.id,
                    )
                    .where(
                        ProductAttributeModel.store_id == store_id,
                        ProductAttributeModel.slug == slug,
                        ProductAttributeModel.status == AttributeStatus.ACTIVE,
                        ProductAttributeModel.deleted_at.is_(None),
                        func.lower(ProductAttributeValueModel.value)
                        == requested_value.casefold(),
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            resolved.append(
                {
                    "attribute_id": row.attribute_id,
                    "attribute_slug": row.attribute_slug,
                    "value_id": row.value_id,
                    "value": row.value,
                }
            )
        return resolved

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
        value_ids = cast(
            Sequence[UUID] | None,
            values.get("attribute_value_ids"),
        )
        for key, value in values.items():
            if key == "attribute_value_ids":
                continue
            setattr(model, key, value)
        if value_ids is not None:
            await self._session.execute(
                delete(ProductVariantAttributeValueModel).where(
                    ProductVariantAttributeValueModel.variant_id == variant_id
                )
            )
            self._session.add_all(
                ProductVariantAttributeValueModel(
                    variant_id=variant_id, attribute_value_id=value_id
                )
                for value_id in value_ids
            )
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return await self._to_domain(model)

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
        return await self._to_domain(model)

    async def _to_domain(self, model: ProductVariantModel) -> ProductVariant:
        rows = (
            await self._session.execute(
                select(ProductAttributeModel.name, ProductAttributeValueModel.value)
                .select_from(ProductVariantAttributeValueModel)
                .join(
                    ProductAttributeValueModel,
                    ProductAttributeValueModel.id
                    == ProductVariantAttributeValueModel.attribute_value_id,
                )
                .join(
                    ProductAttributeModel,
                    ProductAttributeModel.id == ProductAttributeValueModel.attribute_id,
                )
                .where(ProductVariantAttributeValueModel.variant_id == model.id)
                .order_by(ProductAttributeModel.sort_order, ProductAttributeModel.slug)
            )
        ).all()
        return _to_domain(model, {row.name.casefold(): row.value for row in rows})


def _to_domain(
    model: ProductVariantModel, attributes: dict[str, str]
) -> ProductVariant:
    return ProductVariant(
        id=model.id,
        product_id=model.product_id,
        store_id=model.store_id,
        reference=model.reference,
        attributes=attributes,
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
