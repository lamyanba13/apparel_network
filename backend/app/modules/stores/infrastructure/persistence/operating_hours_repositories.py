from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stores.application.operating_hours_repositories import (
    StoreOperatingHoursRepository,
)
from app.modules.stores.application.operating_hours_schemas import StoreHoursCreate
from app.modules.stores.domain.operating_hours import StoreOperatingHours
from app.modules.stores.infrastructure.persistence.operating_hours_models import (
    StoreOperatingHoursModel,
)


class SqlAlchemyStoreOperatingHoursRepository(StoreOperatingHoursRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_scope(
        self,
        store_id: UUID,
        day_of_week: int,
        priority: int,
    ) -> None:
        key = f"store-hours:{store_id}:{day_of_week}:{priority}"
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": key},
        )

    async def add(
        self,
        store_id: UUID,
        values: StoreHoursCreate,
    ) -> StoreOperatingHours:
        model = StoreOperatingHoursModel(
            store_id=store_id,
            day_of_week=values.day_of_week,
            timezone=values.timezone,
            opening_time=values.opening_time,
            closing_time=values.closing_time,
            is_closed=values.is_closed,
            is_24_hours=values.is_24_hours,
            effective_from=values.effective_from,
            effective_until=values.effective_until,
            priority=values.priority,
            notes=values.notes,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _hours(model)

    async def get(
        self,
        store_id: UUID,
        schedule_id: UUID,
    ) -> StoreOperatingHours | None:
        model = await self._session.scalar(
            select(StoreOperatingHoursModel).where(
                StoreOperatingHoursModel.id == schedule_id,
                StoreOperatingHoursModel.store_id == store_id,
                StoreOperatingHoursModel.deleted_at.is_(None),
            )
        )
        return _hours(model) if model is not None else None

    async def list_for_store(
        self,
        store_id: UUID,
        *,
        include_expired: bool = True,
    ) -> Sequence[StoreOperatingHours]:
        statement = select(StoreOperatingHoursModel).where(
            StoreOperatingHoursModel.store_id == store_id,
            StoreOperatingHoursModel.deleted_at.is_(None),
        )
        if not include_expired:
            statement = statement.where(
                (StoreOperatingHoursModel.effective_until.is_(None))
                | (StoreOperatingHoursModel.effective_until > func.now())
            )
        models = await self._session.scalars(
            statement.order_by(
                StoreOperatingHoursModel.day_of_week,
                StoreOperatingHoursModel.priority.desc(),
                StoreOperatingHoursModel.opening_time.asc().nullsfirst(),
                StoreOperatingHoursModel.id,
            )
        )
        return [_hours(model) for model in models]

    async def find_conflicts(
        self,
        store_id: UUID,
        candidate: StoreHoursCreate,
        *,
        exclude_id: UUID | None = None,
    ) -> Sequence[StoreOperatingHours]:
        statement = select(StoreOperatingHoursModel).where(
            StoreOperatingHoursModel.store_id == store_id,
            StoreOperatingHoursModel.day_of_week == candidate.day_of_week,
            StoreOperatingHoursModel.priority == candidate.priority,
            StoreOperatingHoursModel.deleted_at.is_(None),
        )
        if exclude_id is not None:
            statement = statement.where(StoreOperatingHoursModel.id != exclude_id)
        models = await self._session.scalars(statement)
        return [_hours(model) for model in models]

    async def update(
        self,
        store_id: UUID,
        schedule_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> StoreOperatingHours | None:
        result = await self._session.execute(
            update(StoreOperatingHoursModel)
            .where(
                StoreOperatingHoursModel.id == schedule_id,
                StoreOperatingHoursModel.store_id == store_id,
                StoreOperatingHoursModel.deleted_at.is_(None),
                StoreOperatingHoursModel.version == expected_version,
            )
            .values(
                **dict(values),
                updated_at=func.now(),
                version=StoreOperatingHoursModel.version + 1,
            )
            .returning(StoreOperatingHoursModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _hours(model) if model is not None else None

    async def soft_delete(
        self,
        store_id: UUID,
        schedule_id: UUID,
        *,
        deleted_at: datetime,
        expected_version: int,
    ) -> StoreOperatingHours | None:
        result = await self._session.execute(
            update(StoreOperatingHoursModel)
            .where(
                StoreOperatingHoursModel.id == schedule_id,
                StoreOperatingHoursModel.store_id == store_id,
                StoreOperatingHoursModel.deleted_at.is_(None),
                StoreOperatingHoursModel.version == expected_version,
            )
            .values(
                deleted_at=deleted_at,
                updated_at=func.now(),
                version=StoreOperatingHoursModel.version + 1,
            )
            .returning(StoreOperatingHoursModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _hours(model) if model is not None else None


def _hours(model: StoreOperatingHoursModel) -> StoreOperatingHours:
    return StoreOperatingHours(
        id=model.id,
        store_id=model.store_id,
        day_of_week=model.day_of_week,
        timezone=model.timezone,
        opening_time=model.opening_time,
        closing_time=model.closing_time,
        is_closed=model.is_closed,
        is_24_hours=model.is_24_hours,
        effective_from=model.effective_from,
        effective_until=model.effective_until,
        priority=model.priority,
        notes=model.notes,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        version=model.version,
    )
