from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.pricing.application.price_list_schemas import PriceListFilter
from app.modules.pricing.domain import (
    CustomerGroup,
    PriceAssignment,
    PriceList,
    PriceListStatus,
    PriceStatus,
    ResolutionLevel,
    ResolvedPrice,
)
from app.modules.pricing.infrastructure.models import (
    PriceListAssignmentModel,
    PriceListModel,
    ProductPriceModel,
)
from app.modules.products.infrastructure.models import ProductModel
from app.modules.products.infrastructure.variant_models import ProductVariantModel
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyPriceListRepository:
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
        query = select(PriceListModel.id).where(
            PriceListModel.store_id == store_id,
            PriceListModel.slug == slug,
            PriceListModel.deleted_at.is_(None),
        )
        if exclude_id is not None:
            query = query.where(PriceListModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def default_exists(
        self,
        store_id: UUID,
        currency_code: str,
        *,
        exclude_id: UUID | None = None,
    ) -> bool:
        query = select(PriceListModel.id).where(
            PriceListModel.store_id == store_id,
            PriceListModel.currency_code == currency_code,
            PriceListModel.is_default.is_(True),
            PriceListModel.deleted_at.is_(None),
        )
        if exclude_id is not None:
            query = query.where(PriceListModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def priority_conflict_exists(
        self,
        *,
        store_id: UUID,
        currency_code: str,
        customer_group: CustomerGroup,
        priority: int,
        effective_from: datetime | None,
        effective_until: datetime | None,
        exclude_id: UUID | None = None,
    ) -> bool:
        query = select(PriceListModel.id).where(
            PriceListModel.store_id == store_id,
            PriceListModel.currency_code == currency_code,
            PriceListModel.customer_group == customer_group,
            PriceListModel.priority == priority,
            PriceListModel.status == PriceListStatus.ACTIVE,
            PriceListModel.deleted_at.is_(None),
        )
        if effective_from is not None:
            query = query.where(
                or_(
                    PriceListModel.effective_until.is_(None),
                    PriceListModel.effective_until > effective_from,
                )
            )
        if effective_until is not None:
            query = query.where(
                or_(
                    PriceListModel.effective_from.is_(None),
                    PriceListModel.effective_from < effective_until,
                )
            )
        if exclude_id is not None:
            query = query.where(PriceListModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def add(self, values: Mapping[str, object]) -> PriceList:
        persisted = dict(values)
        actor_id = persisted.pop("actor_id", None)
        model = PriceListModel(
            **persisted,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _price_list(model)

    async def list_for_owner(
        self, owner_id: UUID, filters: PriceListFilter
    ) -> tuple[Sequence[PriceList], int]:
        query = (
            select(PriceListModel)
            .join(StoreModel, StoreModel.id == PriceListModel.store_id)
            .where(
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
                PriceListModel.deleted_at.is_(None),
            )
        )
        for field, value in (
            ("store_id", filters.store_id),
            ("currency_code", filters.currency),
            ("status", filters.status),
            ("customer_group", filters.customer_group),
        ):
            if value is not None:
                query = query.where(getattr(PriceListModel, field) == value)
        if filters.effective_at is not None:
            query = query.where(*_effective(PriceListModel, filters.effective_at))
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(
                    PriceListModel.priority.desc(),
                    PriceListModel.effective_from.desc().nullslast(),
                    PriceListModel.id,
                )
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_price_list(row) for row in rows], total

    async def get_for_owner(
        self, price_list_id: UUID, owner_id: UUID
    ) -> PriceList | None:
        model = await self._owned_model(price_list_id, owner_id)
        return _price_list(model) if model else None

    async def update(
        self,
        price_list_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> PriceList | None:
        model = await self._owned_model(price_list_id, owner_id, expected_version)
        if model is None:
            return None
        for key, value in values.items():
            setattr(model, key, value)
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _price_list(model)

    async def archive(
        self,
        price_list_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> PriceList | None:
        model = await self._owned_model(price_list_id, owner_id, expected_version)
        if model is None:
            return None
        model.status = PriceListStatus.ARCHIVED
        model.is_default = False
        model.deleted_at = deleted_at
        model.deleted_by_id = deleted_by_id
        model.updated_by_id = deleted_by_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _price_list(model)

    async def _owned_model(
        self,
        price_list_id: UUID,
        owner_id: UUID,
        expected_version: int | None = None,
    ) -> PriceListModel | None:
        query = (
            select(PriceListModel)
            .join(StoreModel, StoreModel.id == PriceListModel.store_id)
            .where(
                PriceListModel.id == price_list_id,
                PriceListModel.deleted_at.is_(None),
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
            )
        )
        if expected_version is not None:
            query = query.where(PriceListModel.version == expected_version)
        model: PriceListModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def price_context(
        self, price_id: UUID, owner_id: UUID
    ) -> Mapping[str, object] | None:
        row = (
            await self._session.execute(
                select(ProductPriceModel.store_id, ProductPriceModel.currency_code)
                .join(StoreModel, StoreModel.id == ProductPriceModel.store_id)
                .where(
                    ProductPriceModel.id == price_id,
                    ProductPriceModel.deleted_at.is_(None),
                    StoreModel.owner_id == owner_id,
                    StoreModel.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return {"store_id": row.store_id, "currency_code": row.currency_code}

    async def add(
        self, price_list_id: UUID, price_id: UUID, actor_id: UUID
    ) -> PriceAssignment | None:
        if await self._session.scalar(
            select(PriceListAssignmentModel.id).where(
                PriceListAssignmentModel.price_list_id == price_list_id,
                PriceListAssignmentModel.price_id == price_id,
            )
        ):
            return None
        model = PriceListAssignmentModel(
            price_list_id=price_list_id,
            price_id=price_id,
            created_by_id=actor_id,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _assignment(model)

    async def remove(
        self, price_list_id: UUID, price_id: UUID
    ) -> PriceAssignment | None:
        model = await self._session.scalar(
            select(PriceListAssignmentModel).where(
                PriceListAssignmentModel.price_list_id == price_list_id,
                PriceListAssignmentModel.price_id == price_id,
            )
        )
        if model is None:
            return None
        assignment = _assignment(model)
        await self._session.delete(model)
        await self._session.flush()
        return assignment


class SqlAlchemyResolverRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def context_owned(
        self,
        store_id: UUID,
        product_id: UUID,
        variant_id: UUID | None,
        owner_id: UUID,
    ) -> bool:
        product_exists = await self._session.scalar(
            select(ProductModel.id)
            .join(StoreModel, StoreModel.id == ProductModel.store_id)
            .where(
                ProductModel.id == product_id,
                ProductModel.store_id == store_id,
                ProductModel.deleted_at.is_(None),
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
            )
        )
        if product_exists is None:
            return False
        if variant_id is None:
            return True
        return (
            await self._session.scalar(
                select(ProductVariantModel.id).where(
                    ProductVariantModel.id == variant_id,
                    ProductVariantModel.product_id == product_id,
                    ProductVariantModel.store_id == store_id,
                    ProductVariantModel.deleted_at.is_(None),
                    ProductVariantModel.is_active.is_(True),
                )
            )
            is not None
        )

    async def resolve(
        self,
        *,
        store_id: UUID,
        product_id: UUID,
        variant_id: UUID | None,
        currency_code: str,
        customer_group: CustomerGroup,
        timestamp: datetime,
    ) -> ResolvedPrice | None:
        eligible_groups = (
            (CustomerGroup.PUBLIC,)
            if customer_group is CustomerGroup.PUBLIC
            else (customer_group, CustomerGroup.PUBLIC)
        )
        variant_rank = case((ProductPriceModel.variant_id == variant_id, 0), else_=1)
        group_rank = case((PriceListModel.customer_group == customer_group, 0), else_=1)
        assigned = (
            select(ProductPriceModel, PriceListModel)
            .join(
                PriceListAssignmentModel,
                PriceListAssignmentModel.price_id == ProductPriceModel.id,
            )
            .join(
                PriceListModel,
                PriceListModel.id == PriceListAssignmentModel.price_list_id,
            )
            .where(
                ProductPriceModel.store_id == store_id,
                ProductPriceModel.product_id == product_id,
                ProductPriceModel.currency_code == currency_code,
                ProductPriceModel.status == PriceStatus.ACTIVE,
                ProductPriceModel.deleted_at.is_(None),
                PriceListModel.store_id == store_id,
                PriceListModel.currency_code == currency_code,
                PriceListModel.status == PriceListStatus.ACTIVE,
                PriceListModel.customer_group.in_(eligible_groups),
                PriceListModel.deleted_at.is_(None),
                or_(
                    ProductPriceModel.variant_id.is_(None),
                    ProductPriceModel.variant_id == variant_id,
                ),
                *_effective(ProductPriceModel, timestamp),
                *_effective(PriceListModel, timestamp),
            )
            .order_by(
                variant_rank,
                group_rank,
                PriceListModel.priority.desc(),
                PriceListModel.effective_from.desc().nullslast(),
                PriceListModel.id,
            )
            .limit(1)
        )
        row = (await self._session.execute(assigned)).one_or_none()
        if row is not None:
            price, price_list = row
            level = (
                ResolutionLevel.VARIANT
                if price.variant_id is not None
                else ResolutionLevel.PRODUCT
            )
            return _resolved(price, price_list, customer_group, timestamp, level)

        unassigned = (
            select(ProductPriceModel)
            .where(
                ProductPriceModel.store_id == store_id,
                ProductPriceModel.product_id == product_id,
                ProductPriceModel.currency_code == currency_code,
                ProductPriceModel.status == PriceStatus.ACTIVE,
                ProductPriceModel.deleted_at.is_(None),
                or_(
                    ProductPriceModel.variant_id.is_(None),
                    ProductPriceModel.variant_id == variant_id,
                ),
                *_effective(ProductPriceModel, timestamp),
                ~exists().where(
                    PriceListAssignmentModel.price_id == ProductPriceModel.id
                ),
            )
            .order_by(
                variant_rank,
                ProductPriceModel.effective_from.desc().nullslast(),
                ProductPriceModel.id,
            )
            .limit(1)
        )
        price = await self._session.scalar(unassigned)
        return (
            _resolved(
                price,
                None,
                customer_group,
                timestamp,
                ResolutionLevel.DEFAULT_STORE,
            )
            if price
            else None
        )


def _effective(
    model: Any, timestamp: datetime
) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    start = model.effective_from
    end = model.effective_until
    return (
        or_(start.is_(None), start <= timestamp),
        or_(end.is_(None), end > timestamp),
    )


def _price_list(model: PriceListModel) -> PriceList:
    return PriceList(
        id=model.id,
        store_id=model.store_id,
        name=model.name,
        slug=model.slug,
        description=model.description,
        currency_code=model.currency_code,
        priority=model.priority,
        status=model.status,
        customer_group=model.customer_group,
        effective_from=model.effective_from,
        effective_until=model.effective_until,
        is_default=model.is_default,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _assignment(model: PriceListAssignmentModel) -> PriceAssignment:
    return PriceAssignment(
        id=model.id,
        price_list_id=model.price_list_id,
        price_id=model.price_id,
        version=model.version,
        created_at=model.created_at,
        created_by_id=model.created_by_id,
    )


def _resolved(
    price: ProductPriceModel,
    price_list: PriceListModel | None,
    customer_group: CustomerGroup,
    timestamp: datetime,
    level: ResolutionLevel,
) -> ResolvedPrice:
    amount = price.sale_price if price.sale_price is not None else price.base_price
    return ResolvedPrice(
        price_id=price.id,
        price_list_id=price_list.id if price_list else None,
        store_id=price.store_id,
        product_id=price.product_id,
        variant_id=price.variant_id,
        currency_code=price.currency_code,
        customer_group=customer_group,
        amount=Decimal(amount),
        base_price=price.base_price,
        sale_price=price.sale_price,
        tax_class=price.tax_class,
        resolution_level=level,
        price_version=price.version,
        resolved_at=timestamp,
    )
