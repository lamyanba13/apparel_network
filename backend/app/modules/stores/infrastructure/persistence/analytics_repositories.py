from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stores.application.analytics_repositories import (
    StoreAnalyticsRepository,
    StoreAnalyticsSourceRepository,
)
from app.modules.stores.domain.analytics import (
    AnalyticsPeriod,
    AnalyticsSummary,
    DailyMetrics,
    MetricEvent,
    MetricType,
)
from app.modules.stores.domain.media import StoreMediaStatus
from app.modules.stores.domain.membership import StoreMembershipStatus
from app.modules.stores.infrastructure.persistence.analytics_models import (
    StoreDailyMetricsModel,
    StoreMetricEventModel,
)
from app.modules.stores.infrastructure.persistence.media_models import StoreMediaModel
from app.modules.stores.infrastructure.persistence.membership_models import (
    StoreMembershipModel,
)

_COUNTER_FIELDS = (
    "profile_views",
    "gallery_views",
    "media_uploads",
    "staff_invitations",
    "staff_acceptances",
    "verification_submissions",
    "verification_approvals",
    "verification_rejections",
)


class SqlAlchemyStoreAnalyticsRepository(StoreAnalyticsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_event(
        self,
        *,
        event_id: UUID,
        store_id: UUID,
        event_type: MetricType,
        occurred_at: datetime,
        metadata: Mapping[str, JsonValue],
    ) -> MetricEvent | None:
        statement = (
            insert(StoreMetricEventModel)
            .values(
                id=event_id,
                store_id=store_id,
                event_type=event_type,
                occurred_at=occurred_at,
                metadata_=dict(metadata),
            )
            .on_conflict_do_nothing(index_elements=[StoreMetricEventModel.id])
            .returning(StoreMetricEventModel)
        )
        result = await self._session.execute(statement)
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _metric_event(model) if model is not None else None

    async def apply_daily(
        self,
        *,
        store_id: UUID,
        metric_date: date,
        increments: Mapping[str, int],
        storage_bytes: int | None,
        active_members: int | None,
    ) -> tuple[DailyMetrics, bool]:
        initial: dict[str, object] = {
            "store_id": store_id,
            "metric_date": metric_date,
            **{field: increments.get(field, 0) for field in _COUNTER_FIELDS},
            "storage_bytes": storage_bytes or 0,
            "active_members": active_members or 0,
        }
        inserted = await self._session.execute(
            insert(StoreDailyMetricsModel)
            .values(**initial)
            .on_conflict_do_nothing(
                index_elements=[
                    StoreDailyMetricsModel.store_id,
                    StoreDailyMetricsModel.metric_date,
                ]
            )
            .returning(StoreDailyMetricsModel)
        )
        model = inserted.scalar_one_or_none()
        if model is not None:
            await self._session.flush()
            return _daily(model), True

        changes: dict[str, object] = {
            "updated_at": func.now(),
            "version": StoreDailyMetricsModel.version + 1,
        }
        for field, value in increments.items():
            column = getattr(StoreDailyMetricsModel, field)
            changes[field] = column + value
        if storage_bytes is not None:
            changes["storage_bytes"] = storage_bytes
        if active_members is not None:
            changes["active_members"] = active_members
        result = await self._session.execute(
            update(StoreDailyMetricsModel)
            .where(
                StoreDailyMetricsModel.store_id == store_id,
                StoreDailyMetricsModel.metric_date == metric_date,
            )
            .values(**changes)
            .returning(StoreDailyMetricsModel)
        )
        await self._session.flush()
        return _daily(result.scalar_one()), False

    async def list_daily(
        self,
        store_id: UUID,
        *,
        date_from: date,
        date_to: date,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[DailyMetrics], int]:
        where = (
            StoreDailyMetricsModel.store_id == store_id,
            StoreDailyMetricsModel.metric_date.between(date_from, date_to),
        )
        models = await self._session.scalars(
            select(StoreDailyMetricsModel)
            .where(*where)
            .order_by(
                StoreDailyMetricsModel.metric_date.desc(), StoreDailyMetricsModel.id
            )
            .offset(offset)
            .limit(limit)
        )
        total = await self._session.scalar(
            select(func.count()).select_from(StoreDailyMetricsModel).where(*where)
        )
        return [_daily(model) for model in models], int(total or 0)

    async def summarize(
        self,
        store_id: UUID,
        *,
        date_from: date,
        date_to: date,
    ) -> AnalyticsSummary:
        columns = [
            func.coalesce(func.sum(getattr(StoreDailyMetricsModel, field)), 0)
            for field in _COUNTER_FIELDS
        ]
        row = (
            await self._session.execute(
                select(*columns).where(
                    StoreDailyMetricsModel.store_id == store_id,
                    StoreDailyMetricsModel.metric_date.between(date_from, date_to),
                )
            )
        ).one()
        snapshot = await self._session.scalar(
            select(StoreDailyMetricsModel)
            .where(
                StoreDailyMetricsModel.store_id == store_id,
                StoreDailyMetricsModel.metric_date.between(date_from, date_to),
            )
            .order_by(StoreDailyMetricsModel.metric_date.desc())
            .limit(1)
        )
        values = [int(value) for value in row]
        return AnalyticsSummary(
            store_id=store_id,
            period=AnalyticsPeriod(date_from, date_to),
            profile_views=values[0],
            gallery_views=values[1],
            media_uploads=values[2],
            staff_invitations=values[3],
            staff_acceptances=values[4],
            verification_submissions=values[5],
            verification_approvals=values[6],
            verification_rejections=values[7],
            storage_bytes=snapshot.storage_bytes if snapshot is not None else 0,
            active_members=snapshot.active_members if snapshot is not None else 0,
        )

    async def latest_snapshots(self, store_id: UUID) -> tuple[int, int]:
        model = await self._session.scalar(
            select(StoreDailyMetricsModel)
            .where(StoreDailyMetricsModel.store_id == store_id)
            .order_by(StoreDailyMetricsModel.metric_date.desc())
            .limit(1)
        )
        if model is None:
            return 0, 0
        return model.storage_bytes, model.active_members


class SqlAlchemyStoreAnalyticsSourceRepository(StoreAnalyticsSourceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_storage_bytes(self, store_id: UUID) -> int:
        value = await self._session.scalar(
            select(func.coalesce(func.sum(StoreMediaModel.file_size), 0)).where(
                StoreMediaModel.store_id == store_id,
                StoreMediaModel.status == StoreMediaStatus.ACTIVE,
                StoreMediaModel.deleted_at.is_(None),
            )
        )
        return int(value or 0)

    async def active_members(self, store_id: UUID) -> int:
        value = await self._session.scalar(
            select(func.count())
            .select_from(StoreMembershipModel)
            .where(
                StoreMembershipModel.store_id == store_id,
                StoreMembershipModel.status == StoreMembershipStatus.ACTIVE,
            )
        )
        return int(value or 0)


def _daily(model: StoreDailyMetricsModel) -> DailyMetrics:
    return DailyMetrics(
        id=model.id,
        store_id=model.store_id,
        metric_date=model.metric_date,
        profile_views=model.profile_views,
        gallery_views=model.gallery_views,
        media_uploads=model.media_uploads,
        staff_invitations=model.staff_invitations,
        staff_acceptances=model.staff_acceptances,
        verification_submissions=model.verification_submissions,
        verification_approvals=model.verification_approvals,
        verification_rejections=model.verification_rejections,
        storage_bytes=model.storage_bytes,
        active_members=model.active_members,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


def _metric_event(model: StoreMetricEventModel) -> MetricEvent:
    return MetricEvent(
        id=model.id,
        store_id=model.store_id,
        event_type=model.event_type,
        occurred_at=model.occurred_at,
        metadata=dict(model.metadata_),
        created_at=model.created_at,
    )
