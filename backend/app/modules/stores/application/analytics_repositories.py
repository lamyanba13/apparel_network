from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue

from app.modules.stores.domain.analytics import (
    AnalyticsSummary,
    DailyMetrics,
    MetricEvent,
    MetricType,
)


class StoreAnalyticsRepository(Protocol):
    async def record_event(
        self,
        *,
        event_id: UUID,
        store_id: UUID,
        event_type: MetricType,
        occurred_at: datetime,
        metadata: Mapping[str, JsonValue],
    ) -> MetricEvent | None: ...

    async def apply_daily(
        self,
        *,
        store_id: UUID,
        metric_date: date,
        increments: Mapping[str, int],
        storage_bytes: int | None,
        active_members: int | None,
    ) -> tuple[DailyMetrics, bool]: ...

    async def list_daily(
        self,
        store_id: UUID,
        *,
        date_from: date,
        date_to: date,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[DailyMetrics], int]: ...

    async def summarize(
        self, store_id: UUID, *, date_from: date, date_to: date
    ) -> AnalyticsSummary: ...

    async def latest_snapshots(self, store_id: UUID) -> tuple[int, int]: ...


class StoreAnalyticsSourceRepository(Protocol):
    async def active_storage_bytes(self, store_id: UUID) -> int: ...

    async def active_members(self, store_id: UUID) -> int: ...
