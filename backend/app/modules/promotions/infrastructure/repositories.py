from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.catalogs.infrastructure.taxonomy_models import ProductCategoryModel
from app.modules.orders.domain import OrderStatus
from app.modules.orders.infrastructure.models import OrderModel
from app.modules.products.domain import OutboxStatus
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.products.infrastructure.models import ProductModel
from app.modules.promotions.application.schemas import CouponFilter, PromotionFilter
from app.modules.promotions.domain import (
    Promotion,
    PromotionCoupon,
    PromotionCustomerUsage,
    PromotionEvent,
    PromotionRedemption,
    PromotionRule,
    PromotionStatus,
)
from app.modules.promotions.infrastructure.models import (
    PromotionCouponModel,
    PromotionCustomerUsageModel,
    PromotionModel,
    PromotionRedemptionModel,
    PromotionRuleModel,
)
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyPromotionRepository:
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

    async def add(self, values: Mapping[str, object]) -> Promotion:
        model = PromotionModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _promotion(model)

    async def get_for_owner(
        self, promotion_id: UUID, owner_id: UUID
    ) -> Promotion | None:
        model = await self._owned_model(promotion_id, owner_id)
        return _promotion(model) if model else None

    async def list_for_owner(
        self, owner_id: UUID, filters: PromotionFilter
    ) -> tuple[Sequence[Promotion], int]:
        query = (
            select(PromotionModel)
            .join(StoreModel, StoreModel.id == PromotionModel.store_id)
            .where(
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
                PromotionModel.deleted_at.is_(None),
            )
        )
        if filters.store_id is not None:
            query = query.where(PromotionModel.store_id == filters.store_id)
        if filters.status is not None:
            query = query.where(PromotionModel.status == filters.status)
        if filters.promotion_type is not None:
            query = query.where(PromotionModel.promotion_type == filters.promotion_type)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(PromotionModel.priority.desc(), PromotionModel.id)
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_promotion(row) for row in rows], total

    async def list_active(self, store_id: UUID, at: datetime) -> Sequence[Promotion]:
        rows = (
            await self._session.scalars(
                select(PromotionModel)
                .where(
                    PromotionModel.store_id == store_id,
                    PromotionModel.status == PromotionStatus.ACTIVE,
                    PromotionModel.deleted_at.is_(None),
                    or_(
                        PromotionModel.effective_from.is_(None),
                        PromotionModel.effective_from <= at,
                    ),
                    or_(
                        PromotionModel.effective_until.is_(None),
                        PromotionModel.effective_until > at,
                    ),
                )
                .order_by(PromotionModel.priority.desc(), PromotionModel.id)
            )
        ).all()
        return [_promotion(row) for row in rows]

    async def update(
        self,
        promotion_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> Promotion | None:
        model = await self._owned_model(promotion_id, owner_id, expected_version)
        if model is None:
            return None
        for field, value in values.items():
            setattr(model, field, value)
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _promotion(model)

    async def transition(
        self,
        promotion_id: UUID,
        owner_id: UUID,
        *,
        status: PromotionStatus,
        expected_version: int,
        actor_id: UUID,
    ) -> Promotion | None:
        return await self.update(
            promotion_id,
            owner_id,
            values={"status": status, "updated_by_id": actor_id},
            expected_version=expected_version,
        )

    async def archive(
        self,
        promotion_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> Promotion | None:
        return await self.update(
            promotion_id,
            owner_id,
            values={
                "status": PromotionStatus.ARCHIVED,
                "deleted_at": deleted_at,
                "deleted_by_id": deleted_by_id,
                "updated_by_id": deleted_by_id,
            },
            expected_version=expected_version,
        )

    async def _owned_model(
        self, promotion_id: UUID, owner_id: UUID, version: int | None = None
    ) -> PromotionModel | None:
        query = (
            select(PromotionModel)
            .join(StoreModel, StoreModel.id == PromotionModel.store_id)
            .where(
                PromotionModel.id == promotion_id,
                PromotionModel.deleted_at.is_(None),
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
            )
        )
        if version is not None:
            query = query.where(PromotionModel.version == version)
        model: PromotionModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyPromotionRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(
        self, promotion_id: UUID, values: Sequence[Mapping[str, object]]
    ) -> Sequence[PromotionRule]:
        models = [
            PromotionRuleModel(promotion_id=promotion_id, **dict(value))
            for value in values
        ]
        self._session.add_all(models)
        await self._session.flush()
        for model in models:
            await self._session.refresh(model)
        return [_rule(model) for model in models]

    async def list_for_promotions(
        self, promotion_ids: Sequence[UUID]
    ) -> Mapping[UUID, Sequence[PromotionRule]]:
        if not promotion_ids:
            return {}
        rows = (
            await self._session.scalars(
                select(PromotionRuleModel)
                .where(
                    PromotionRuleModel.promotion_id.in_(promotion_ids),
                    PromotionRuleModel.deleted_at.is_(None),
                )
                .order_by(PromotionRuleModel.created_at, PromotionRuleModel.id)
            )
        ).all()
        grouped: defaultdict[UUID, list[PromotionRule]] = defaultdict(list)
        for row in rows:
            grouped[row.promotion_id].append(_rule(row))
        return grouped


class SqlAlchemyPromotionCouponRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, values: Mapping[str, object]) -> PromotionCoupon:
        model = PromotionCouponModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _coupon(model)

    async def code_exists(
        self, store_id: UUID, code: str, exclude_id: UUID | None = None
    ) -> bool:
        query = select(PromotionCouponModel.id).where(
            PromotionCouponModel.store_id == store_id,
            PromotionCouponModel.code == code,
            PromotionCouponModel.deleted_at.is_(None),
        )
        if exclude_id is not None:
            query = query.where(PromotionCouponModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def get_for_owner(
        self, coupon_id: UUID, owner_id: UUID
    ) -> PromotionCoupon | None:
        model = await self._owned_model(coupon_id, owner_id)
        return _coupon(model) if model else None

    async def list_for_owner(
        self, owner_id: UUID, filters: CouponFilter
    ) -> tuple[Sequence[PromotionCoupon], int]:
        query = (
            select(PromotionCouponModel)
            .join(StoreModel, StoreModel.id == PromotionCouponModel.store_id)
            .where(
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
                PromotionCouponModel.deleted_at.is_(None),
            )
        )
        if filters.store_id is not None:
            query = query.where(PromotionCouponModel.store_id == filters.store_id)
        if filters.promotion_id is not None:
            query = query.where(
                PromotionCouponModel.promotion_id == filters.promotion_id
            )
        if filters.active is not None:
            query = query.where(PromotionCouponModel.active == filters.active)
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(
                    PromotionCouponModel.created_at.desc(), PromotionCouponModel.id
                )
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_coupon(row) for row in rows], total

    async def list_by_codes(
        self, store_id: UUID, codes: Sequence[str]
    ) -> Sequence[PromotionCoupon]:
        if not codes:
            return []
        rows = (
            await self._session.scalars(
                select(PromotionCouponModel)
                .where(
                    PromotionCouponModel.store_id == store_id,
                    PromotionCouponModel.code.in_(codes),
                    PromotionCouponModel.deleted_at.is_(None),
                )
                .order_by(PromotionCouponModel.code, PromotionCouponModel.id)
            )
        ).all()
        return [_coupon(row) for row in rows]

    async def update(
        self,
        coupon_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> PromotionCoupon | None:
        model = await self._owned_model(coupon_id, owner_id, expected_version)
        if model is None:
            return None
        for field, value in values.items():
            setattr(model, field, value)
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _coupon(model)

    async def archive(
        self,
        coupon_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime,
        deleted_by_id: UUID,
    ) -> PromotionCoupon | None:
        return await self.update(
            coupon_id,
            owner_id,
            values={
                "active": False,
                "deleted_at": deleted_at,
                "deleted_by_id": deleted_by_id,
                "updated_by_id": deleted_by_id,
            },
            expected_version=expected_version,
        )

    async def _owned_model(
        self, coupon_id: UUID, owner_id: UUID, version: int | None = None
    ) -> PromotionCouponModel | None:
        query = (
            select(PromotionCouponModel)
            .join(StoreModel, StoreModel.id == PromotionCouponModel.store_id)
            .where(
                PromotionCouponModel.id == coupon_id,
                PromotionCouponModel.deleted_at.is_(None),
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
            )
        )
        if version is not None:
            query = query.where(PromotionCouponModel.version == version)
        model: PromotionCouponModel | None = await self._session.scalar(query)
        return model


class SqlAlchemyPromotionRedemptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_limits(
        self, promotion_ids: Sequence[UUID], coupon_ids: Sequence[UUID]
    ) -> None:
        if promotion_ids:
            await self._session.scalars(
                select(PromotionModel.id)
                .where(PromotionModel.id.in_(promotion_ids))
                .order_by(PromotionModel.id)
                .with_for_update()
            )
        if coupon_ids:
            await self._session.scalars(
                select(PromotionCouponModel.id)
                .where(PromotionCouponModel.id.in_(coupon_ids))
                .order_by(PromotionCouponModel.id)
                .with_for_update()
            )

    async def promotion_usage(self, promotion_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count(PromotionRedemptionModel.id)).where(
                    PromotionRedemptionModel.promotion_id == promotion_id,
                    PromotionRedemptionModel.deleted_at.is_(None),
                )
            )
            or 0
        )

    async def coupon_usage(self, coupon_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count(PromotionRedemptionModel.id)).where(
                    PromotionRedemptionModel.coupon_id == coupon_id,
                    PromotionRedemptionModel.deleted_at.is_(None),
                )
            )
            or 0
        )

    async def customer_promotion_usage(
        self, promotion_id: UUID, customer_id: UUID
    ) -> int:
        return int(
            await self._session.scalar(
                select(
                    func.coalesce(func.sum(PromotionCustomerUsageModel.usage_count), 0)
                ).where(
                    PromotionCustomerUsageModel.promotion_id == promotion_id,
                    PromotionCustomerUsageModel.customer_id == customer_id,
                    PromotionCustomerUsageModel.deleted_at.is_(None),
                )
            )
            or 0
        )

    async def customer_usage(
        self, promotion_id: UUID, customer_id: UUID, coupon_id: UUID | None
    ) -> int:
        query = select(PromotionCustomerUsageModel.usage_count).where(
            PromotionCustomerUsageModel.promotion_id == promotion_id,
            PromotionCustomerUsageModel.customer_id == customer_id,
            PromotionCustomerUsageModel.deleted_at.is_(None),
        )
        query = query.where(
            PromotionCustomerUsageModel.coupon_id == coupon_id
            if coupon_id is not None
            else PromotionCustomerUsageModel.coupon_id.is_(None)
        )
        return int(await self._session.scalar(query) or 0)

    async def completed_order_count(self, customer_id: UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count(OrderModel.id)).where(
                    OrderModel.customer_id == customer_id,
                    OrderModel.status == OrderStatus.CONFIRMED,
                    OrderModel.deleted_at.is_(None),
                )
            )
            or 0
        )

    async def item_contexts(
        self, product_ids: Sequence[UUID]
    ) -> Mapping[UUID, Mapping[str, object]]:
        if not product_ids:
            return {}
        product_rows = (
            await self._session.execute(
                select(
                    ProductModel.id, ProductModel.catalog_id, ProductModel.brand
                ).where(
                    ProductModel.id.in_(product_ids), ProductModel.deleted_at.is_(None)
                )
            )
        ).all()
        category_rows = (
            await self._session.execute(
                select(
                    ProductCategoryModel.product_id, ProductCategoryModel.category_id
                ).where(ProductCategoryModel.product_id.in_(product_ids))
            )
        ).all()
        categories: defaultdict[UUID, list[UUID]] = defaultdict(list)
        for row in category_rows:
            categories[row.product_id].append(row.category_id)
        return {
            row.id: {
                "catalog_id": row.catalog_id,
                "brand": row.brand,
                "category_ids": tuple(categories[row.id]),
            }
            for row in product_rows
        }

    async def add(self, values: Mapping[str, object]) -> PromotionRedemption:
        model = PromotionRedemptionModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _redemption(model)

    async def increment_usage(
        self,
        promotion_id: UUID,
        coupon_id: UUID | None,
        customer_id: UUID,
        store_id: UUID,
    ) -> PromotionCustomerUsage:
        query = select(PromotionCustomerUsageModel).where(
            PromotionCustomerUsageModel.promotion_id == promotion_id,
            PromotionCustomerUsageModel.customer_id == customer_id,
            PromotionCustomerUsageModel.deleted_at.is_(None),
        )
        query = query.where(
            PromotionCustomerUsageModel.coupon_id == coupon_id
            if coupon_id is not None
            else PromotionCustomerUsageModel.coupon_id.is_(None)
        )
        model = await self._session.scalar(query.with_for_update())
        if model is None:
            model = PromotionCustomerUsageModel(
                promotion_id=promotion_id,
                coupon_id=coupon_id,
                customer_id=customer_id,
                store_id=store_id,
                usage_count=1,
                created_by_id=customer_id,
                updated_by_id=customer_id,
            )
            self._session.add(model)
        else:
            model.usage_count += 1
            model.version += 1
            model.updated_by_id = customer_id
        await self._session.flush()
        await self._session.refresh(model)
        return _usage(model)

    async def link_order(
        self, checkout_session_id: UUID, order_id: UUID, customer_id: UUID
    ) -> Sequence[PromotionRedemption]:
        models = (
            await self._session.scalars(
                select(PromotionRedemptionModel)
                .where(
                    PromotionRedemptionModel.checkout_session_id == checkout_session_id,
                    PromotionRedemptionModel.customer_id == customer_id,
                    PromotionRedemptionModel.order_id.is_(None),
                    PromotionRedemptionModel.deleted_at.is_(None),
                )
                .with_for_update()
            )
        ).all()
        for model in models:
            model.order_id = order_id
            model.updated_by_id = customer_id
            model.version += 1
        await self._session.flush()
        for model in models:
            await self._session.refresh(model)
        return [_redemption(model) for model in models]

    async def list_for_checkout(
        self, checkout_session_id: UUID, customer_id: UUID
    ) -> Sequence[PromotionRedemption]:
        return await self._list(
            PromotionRedemptionModel.checkout_session_id == checkout_session_id,
            customer_id,
        )

    async def list_for_order(
        self, order_id: UUID, customer_id: UUID
    ) -> Sequence[PromotionRedemption]:
        return await self._list(
            PromotionRedemptionModel.order_id == order_id, customer_id
        )

    async def _list(
        self, predicate: ColumnElement[bool], customer_id: UUID
    ) -> Sequence[PromotionRedemption]:
        rows = (
            await self._session.scalars(
                select(PromotionRedemptionModel)
                .where(
                    predicate,
                    PromotionRedemptionModel.customer_id == customer_id,
                    PromotionRedemptionModel.deleted_at.is_(None),
                )
                .order_by(
                    PromotionRedemptionModel.created_at, PromotionRedemptionModel.id
                )
            )
        ).all()
        return [_redemption(row) for row in rows]


class SqlAlchemyPromotionOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: PromotionEvent) -> None:
        self._session.add(
            EventOutboxModel(
                id=event.event_id,
                aggregate_type="promotion",
                aggregate_id=event.promotion_id,
                event_name=event.event_name,
                payload=cast(dict[str, object], event.payload),
                occurred_at=event.occurred_at,
                status=OutboxStatus.PENDING,
            )
        )
        await self._session.flush()


def _promotion(model: PromotionModel) -> Promotion:
    return Promotion(
        id=model.id,
        store_id=model.store_id,
        name=model.name,
        description=model.description,
        promotion_type=model.promotion_type,
        status=model.status,
        currency=model.currency,
        percentage=model.percentage,
        fixed_amount=model.fixed_amount,
        buy_quantity=model.buy_quantity,
        get_quantity=model.get_quantity,
        bundle_quantity=model.bundle_quantity,
        bundle_price=model.bundle_price,
        tiers=tuple(cast(list[dict[str, JsonValue]], model.tiers)),
        public=model.public,
        first_purchase_only=model.first_purchase_only,
        customer_group=model.customer_group,
        minimum_order_amount=model.minimum_order_amount,
        minimum_quantity=model.minimum_quantity,
        maximum_discount=model.maximum_discount,
        usage_limit=model.usage_limit,
        per_customer_usage_limit=model.per_customer_usage_limit,
        exclusive=model.exclusive,
        stackable=model.stackable,
        priority=model.priority,
        maximum_stack=model.maximum_stack,
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


def _rule(model: PromotionRuleModel) -> PromotionRule:
    return PromotionRule(
        id=model.id,
        promotion_id=model.promotion_id,
        condition=model.condition,
        configuration=cast(dict[str, JsonValue], model.configuration),
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _coupon(model: PromotionCouponModel) -> PromotionCoupon:
    return PromotionCoupon(
        id=model.id,
        promotion_id=model.promotion_id,
        store_id=model.store_id,
        code=model.code,
        active=model.active,
        effective_from=model.effective_from,
        effective_until=model.effective_until,
        usage_limit=model.usage_limit,
        per_customer_usage_limit=model.per_customer_usage_limit,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _redemption(model: PromotionRedemptionModel) -> PromotionRedemption:
    return PromotionRedemption(
        id=model.id,
        promotion_id=model.promotion_id,
        coupon_id=model.coupon_id,
        customer_id=model.customer_id,
        store_id=model.store_id,
        cart_id=model.cart_id,
        checkout_session_id=model.checkout_session_id,
        order_id=model.order_id,
        discount_amount=model.discount_amount,
        currency=model.currency,
        coupon_code=model.coupon_code,
        snapshot=cast(dict[str, JsonValue], model.snapshot),
        redeemed_at=model.redeemed_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _usage(model: PromotionCustomerUsageModel) -> PromotionCustomerUsage:
    return PromotionCustomerUsage(
        id=model.id,
        promotion_id=model.promotion_id,
        coupon_id=model.coupon_id,
        customer_id=model.customer_id,
        store_id=model.store_id,
        usage_count=model.usage_count,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )
