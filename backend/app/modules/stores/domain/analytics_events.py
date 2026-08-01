from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7

from app.modules.stores.domain.analytics import MetricType


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreAnalyticsEvent:
    store_id: UUID
    metric_type: MetricType
    metric_date: date
    value: int
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None

    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "store_id": str(self.store_id),
            "metric_type": self.metric_type.value,
            "metric_date": self.metric_date.isoformat(),
            "value": self.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMetricRecorded(StoreAnalyticsEvent):
    event_name: ClassVar[str] = "store.metric.recorded"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreAnalyticsUpdated(StoreAnalyticsEvent):
    event_name: ClassVar[str] = "store.analytics.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class DailyMetricsCreated(StoreAnalyticsEvent):
    event_name: ClassVar[str] = "store.analytics.daily.created"
