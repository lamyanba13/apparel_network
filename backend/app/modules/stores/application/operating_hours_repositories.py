from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.stores.application.operating_hours_schemas import StoreHoursCreate
from app.modules.stores.domain.operating_hours import StoreOperatingHours


class StoreOperatingHoursRepository(Protocol):
    async def lock_scope(
        self,
        store_id: UUID,
        day_of_week: int,
        priority: int,
    ) -> None: ...

    async def add(
        self,
        store_id: UUID,
        values: StoreHoursCreate,
    ) -> StoreOperatingHours: ...

    async def get(
        self,
        store_id: UUID,
        schedule_id: UUID,
    ) -> StoreOperatingHours | None: ...

    async def list_for_store(
        self,
        store_id: UUID,
        *,
        include_expired: bool = True,
    ) -> Sequence[StoreOperatingHours]: ...

    async def find_conflicts(
        self,
        store_id: UUID,
        candidate: StoreHoursCreate,
        *,
        exclude_id: UUID | None = None,
    ) -> Sequence[StoreOperatingHours]: ...

    async def update(
        self,
        store_id: UUID,
        schedule_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> StoreOperatingHours | None: ...

    async def soft_delete(
        self,
        store_id: UUID,
        schedule_id: UUID,
        *,
        deleted_at: datetime,
        expected_version: int,
    ) -> StoreOperatingHours | None: ...
