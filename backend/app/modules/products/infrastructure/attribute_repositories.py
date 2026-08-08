from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.products.domain import (
    AttributeStatus,
    OutboxEvent,
    OutboxStatus,
    ProductAttribute,
    ProductAttributeValue,
    VariantAttributeAssignment,
    VariantAttributeValue,
)
from app.modules.products.domain.variant_events import VariantEvent
from app.modules.products.infrastructure.attribute_models import (
    EventOutboxModel,
    ProductAttributeModel,
    ProductAttributeValueModel,
    ProductVariantAttributeValueModel,
)
from app.modules.products.infrastructure.variant_models import ProductVariantModel
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyAttributeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store_owned(self, store_id: UUID, owner_id: UUID) -> bool:
        return (
            await self._session.scalar(
                select(StoreModel.id).where(
                    StoreModel.id == store_id,
                    StoreModel.owner_id == owner_id,
                    StoreModel.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def slug_exists(
        self, store_id: UUID, slug: str, *, exclude_id: UUID | None = None
    ) -> bool:
        query = select(ProductAttributeModel.id).where(
            ProductAttributeModel.store_id == store_id,
            ProductAttributeModel.slug == slug,
        )
        if exclude_id is not None:
            query = query.where(ProductAttributeModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def add(self, values: Mapping[str, object]) -> ProductAttribute:
        persisted = dict(values)
        actor_id = persisted.pop("actor_id", None)
        model = ProductAttributeModel(
            **persisted,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _attribute(model)

    async def list_for_owner(
        self, owner_id: UUID, *, store_id: UUID | None = None
    ) -> Sequence[ProductAttribute]:
        query = (
            select(ProductAttributeModel)
            .join(StoreModel, StoreModel.id == ProductAttributeModel.store_id)
            .where(
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
                ProductAttributeModel.deleted_at.is_(None),
            )
        )
        if store_id is not None:
            query = query.where(ProductAttributeModel.store_id == store_id)
        rows = (
            await self._session.scalars(
                query.order_by(
                    ProductAttributeModel.sort_order,
                    ProductAttributeModel.name,
                    ProductAttributeModel.id,
                )
            )
        ).all()
        return [_attribute(row) for row in rows]

    async def get_for_owner(
        self, attribute_id: UUID, owner_id: UUID
    ) -> ProductAttribute | None:
        model = await self._owned_model(attribute_id, owner_id)
        return _attribute(model) if model else None

    async def update(
        self,
        attribute_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> ProductAttribute | None:
        model = await self._owned_model(attribute_id, owner_id, expected_version)
        if model is None:
            return None
        for key, value in values.items():
            setattr(model, key, value)
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _attribute(model)

    async def archive(
        self,
        attribute_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> ProductAttribute | None:
        model = await self._owned_model(attribute_id, owner_id, expected_version)
        if model is None:
            return None
        model.status = AttributeStatus.ARCHIVED
        model.deleted_at = deleted_at
        model.deleted_by_id = deleted_by_id
        model.updated_by_id = deleted_by_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _attribute(model)

    async def _owned_model(
        self,
        attribute_id: UUID,
        owner_id: UUID,
        expected_version: int | None = None,
    ) -> ProductAttributeModel | None:
        query = (
            select(ProductAttributeModel)
            .join(StoreModel, StoreModel.id == ProductAttributeModel.store_id)
            .where(
                ProductAttributeModel.id == attribute_id,
                ProductAttributeModel.deleted_at.is_(None),
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
            )
        )
        if expected_version is not None:
            query = query.where(ProductAttributeModel.version == expected_version)
        model: ProductAttributeModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyAttributeValueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def value_exists(
        self, attribute_id: UUID, value: str, *, exclude_id: UUID | None = None
    ) -> bool:
        query = select(ProductAttributeValueModel.id).where(
            ProductAttributeValueModel.attribute_id == attribute_id,
            func.lower(ProductAttributeValueModel.value) == value.casefold(),
        )
        if exclude_id is not None:
            query = query.where(ProductAttributeValueModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def slug_exists(
        self, attribute_id: UUID, slug: str, *, exclude_id: UUID | None = None
    ) -> bool:
        query = select(ProductAttributeValueModel.id).where(
            ProductAttributeValueModel.attribute_id == attribute_id,
            ProductAttributeValueModel.slug == slug,
        )
        if exclude_id is not None:
            query = query.where(ProductAttributeValueModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def add(
        self, attribute_id: UUID, values: Mapping[str, object]
    ) -> ProductAttributeValue:
        model = ProductAttributeValueModel(attribute_id=attribute_id, **dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _value(model)

    async def get_for_owner(
        self, value_id: UUID, owner_id: UUID
    ) -> ProductAttributeValue | None:
        model = await self._owned_model(value_id, owner_id)
        return _value(model) if model else None

    async def update(
        self,
        value_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> ProductAttributeValue | None:
        model = await self._owned_model(value_id, owner_id, expected_version)
        if model is None:
            return None
        for key, value in values.items():
            setattr(model, key, value)
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _value(model)

    async def delete(
        self, value_id: UUID, owner_id: UUID, *, expected_version: int
    ) -> bool | None:
        model = await self._owned_model(value_id, owner_id, expected_version)
        if model is None:
            return None
        assigned = await self._session.scalar(
            select(
                exists().where(
                    ProductVariantAttributeValueModel.attribute_value_id == value_id
                )
            )
        )
        if assigned:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def _owned_model(
        self,
        value_id: UUID,
        owner_id: UUID,
        expected_version: int | None = None,
    ) -> ProductAttributeValueModel | None:
        query = (
            select(ProductAttributeValueModel)
            .join(
                ProductAttributeModel,
                ProductAttributeModel.id == ProductAttributeValueModel.attribute_id,
            )
            .join(StoreModel, StoreModel.id == ProductAttributeModel.store_id)
            .where(
                ProductAttributeValueModel.id == value_id,
                ProductAttributeModel.deleted_at.is_(None),
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
            )
        )
        if expected_version is not None:
            query = query.where(ProductAttributeValueModel.version == expected_version)
        model: ProductAttributeValueModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyVariantAttributeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def variant_context(
        self, variant_id: UUID, owner_id: UUID
    ) -> Mapping[str, object] | None:
        row = (
            await self._session.execute(
                select(
                    ProductVariantModel.product_id,
                    ProductVariantModel.store_id,
                    ProductVariantModel.version,
                )
                .join(StoreModel, StoreModel.id == ProductVariantModel.store_id)
                .where(
                    ProductVariantModel.id == variant_id,
                    ProductVariantModel.deleted_at.is_(None),
                    StoreModel.owner_id == owner_id,
                    StoreModel.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return {
            "product_id": row.product_id,
            "store_id": row.store_id,
            "version": row.version,
        }

    async def value_context(
        self, value_id: UUID, owner_id: UUID
    ) -> Mapping[str, object] | None:
        row = (
            await self._session.execute(
                select(
                    ProductAttributeValueModel.attribute_id,
                    ProductAttributeModel.store_id,
                )
                .join(
                    ProductAttributeModel,
                    ProductAttributeModel.id == ProductAttributeValueModel.attribute_id,
                )
                .join(StoreModel, StoreModel.id == ProductAttributeModel.store_id)
                .where(
                    ProductAttributeValueModel.id == value_id,
                    ProductAttributeModel.status == AttributeStatus.ACTIVE,
                    ProductAttributeModel.deleted_at.is_(None),
                    StoreModel.owner_id == owner_id,
                    StoreModel.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return {"attribute_id": row.attribute_id, "store_id": row.store_id}

    async def list_for_variant(
        self, variant_id: UUID, owner_id: UUID
    ) -> Sequence[VariantAttributeValue] | None:
        if await self.variant_context(variant_id, owner_id) is None:
            return None
        rows = (
            await self._session.execute(
                select(
                    ProductVariantAttributeValueModel,
                    ProductAttributeValueModel,
                    ProductAttributeModel,
                )
                .join(
                    ProductAttributeValueModel,
                    ProductAttributeValueModel.id
                    == ProductVariantAttributeValueModel.attribute_value_id,
                )
                .join(
                    ProductAttributeModel,
                    ProductAttributeModel.id == ProductAttributeValueModel.attribute_id,
                )
                .where(ProductVariantAttributeValueModel.variant_id == variant_id)
                .order_by(
                    ProductAttributeModel.sort_order,
                    ProductAttributeModel.slug,
                    ProductAttributeValueModel.sort_order,
                    ProductAttributeValueModel.slug,
                )
            )
        ).all()
        return [
            _variant_value(assignment, value, attribute)
            for assignment, value, attribute in rows
        ]

    async def combination_exists(
        self, product_id: UUID, signature: str, *, exclude_id: UUID
    ) -> bool:
        return (
            await self._session.scalar(
                select(ProductVariantModel.id).where(
                    ProductVariantModel.product_id == product_id,
                    ProductVariantModel.attribute_signature == signature,
                    ProductVariantModel.id != exclude_id,
                    ProductVariantModel.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def assign(
        self,
        variant_id: UUID,
        value_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        signature: str,
    ) -> VariantAttributeAssignment | None:
        variant = await self._versioned_variant(variant_id, owner_id, expected_version)
        if variant is None:
            return None
        model = ProductVariantAttributeValueModel(
            variant_id=variant_id, attribute_value_id=value_id
        )
        self._session.add(model)
        variant.attribute_signature = signature
        variant.updated_by_id = owner_id
        variant.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _assignment(model)

    async def remove(
        self,
        variant_id: UUID,
        value_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        signature: str,
    ) -> VariantAttributeAssignment | None:
        variant = await self._versioned_variant(variant_id, owner_id, expected_version)
        if variant is None:
            return None
        model = await self._session.scalar(
            select(ProductVariantAttributeValueModel).where(
                ProductVariantAttributeValueModel.variant_id == variant_id,
                ProductVariantAttributeValueModel.attribute_value_id == value_id,
            )
        )
        if model is None:
            return None
        assignment = _assignment(model)
        await self._session.delete(model)
        variant.attribute_signature = signature
        variant.updated_by_id = owner_id
        variant.version += 1
        await self._session.flush()
        return assignment

    async def _versioned_variant(
        self, variant_id: UUID, owner_id: UUID, expected_version: int
    ) -> ProductVariantModel | None:
        model: ProductVariantModel | None = await self._session.scalar(
            select(ProductVariantModel)
            .join(StoreModel, StoreModel.id == ProductVariantModel.store_id)
            .where(
                ProductVariantModel.id == variant_id,
                ProductVariantModel.deleted_at.is_(None),
                ProductVariantModel.version == expected_version,
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
            )
        )
        return model


class SqlAlchemyOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: VariantEvent) -> OutboxEvent:
        model = EventOutboxModel(
            id=event.event_id,
            aggregate_type="product_variant",
            aggregate_id=event.aggregate_id,
            event_name=event.event_name,
            payload=cast(dict[str, object], event.payload),
            occurred_at=event.occurred_at,
            status=OutboxStatus.PENDING,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _outbox(model)


def _attribute(model: ProductAttributeModel) -> ProductAttribute:
    return ProductAttribute(
        id=model.id,
        store_id=model.store_id,
        name=model.name,
        slug=model.slug,
        attribute_type=model.attribute_type,
        description=model.description,
        required=model.required,
        filterable=model.filterable,
        searchable=model.searchable,
        sort_order=model.sort_order,
        status=model.status,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _value(model: ProductAttributeValueModel) -> ProductAttributeValue:
    return ProductAttributeValue(
        id=model.id,
        attribute_id=model.attribute_id,
        value=model.value,
        slug=model.slug,
        sort_order=model.sort_order,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _assignment(
    model: ProductVariantAttributeValueModel,
) -> VariantAttributeAssignment:
    return VariantAttributeAssignment(
        id=model.id,
        variant_id=model.variant_id,
        attribute_value_id=model.attribute_value_id,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _variant_value(
    assignment: ProductVariantAttributeValueModel,
    value: ProductAttributeValueModel,
    attribute: ProductAttributeModel,
) -> VariantAttributeValue:
    return VariantAttributeValue(
        assignment_id=assignment.id,
        attribute_id=attribute.id,
        attribute_name=attribute.name,
        attribute_slug=attribute.slug,
        attribute_type=attribute.attribute_type,
        attribute_sort_order=attribute.sort_order,
        value_id=value.id,
        value=value.value,
        value_slug=value.slug,
        value_sort_order=value.sort_order,
    )


def _outbox(model: EventOutboxModel) -> OutboxEvent:
    return OutboxEvent(
        id=model.id,
        aggregate_type=model.aggregate_type,
        aggregate_id=model.aggregate_id,
        event_name=model.event_name,
        payload=model.payload,
        occurred_at=model.occurred_at,
        published_at=model.published_at,
        status=model.status,
        retry_count=model.retry_count,
        version=model.version,
        available_at=model.available_at,
        attempts=model.attempts,
        locked_at=model.locked_at,
        locked_by=model.locked_by,
        dispatched_at=model.dispatched_at,
        last_error=model.last_error,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
