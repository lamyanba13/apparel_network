from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7

from app.common.context import maybe_get_request_context
from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.stores.application.analytics_repositories import (
    StoreAnalyticsRepository,
    StoreAnalyticsSourceRepository,
)
from app.modules.stores.application.repositories import StoreRepository
from app.modules.stores.domain.analytics import (
    AnalyticsPeriod,
    AnalyticsSummary,
    DailyMetrics,
    MetricEvent,
    MetricType,
    StoreAnalytics,
)
from app.modules.stores.domain.analytics_events import (
    DailyMetricsCreated,
    StoreAnalyticsEvent,
    StoreAnalyticsUpdated,
    StoreMetricRecorded,
)
from app.observability.metrics import (
    STORE_DAILY_UPDATES,
    STORE_METRIC_EVENTS,
    STORE_PROFILE_VIEWS,
    STORE_STORAGE_BYTES,
)

_INCREMENT_FIELDS: dict[MetricType, str] = {
    MetricType.PROFILE_VIEW: "profile_views",
    MetricType.GALLERY_VIEW: "gallery_views",
    MetricType.MEDIA_UPLOAD: "media_uploads",
    MetricType.STAFF_INVITATION: "staff_invitations",
    MetricType.STAFF_ACCEPTANCE: "staff_acceptances",
    MetricType.VERIFICATION_SUBMISSION: "verification_submissions",
    MetricType.VERIFICATION_APPROVAL: "verification_approvals",
    MetricType.VERIFICATION_REJECTION: "verification_rejections",
}
_SENSITIVE_METADATA_PARTS = {
    "email",
    "token",
    "password",
    "secret",
    "ip",
    "user_agent",
    "authorization",
    "cookie",
}


class StoreAnalyticsAuditService:
    def __init__(self, events: EventPublisher) -> None:
        self._events = events

    async def publish(
        self,
        event_type: type[StoreAnalyticsEvent],
        *,
        store_id: UUID,
        metric_type: MetricType,
        metric_date: date,
        value: int,
        occurred_at: datetime,
    ) -> None:
        context = maybe_get_request_context()
        await self._events.publish(
            event_type(
                store_id=store_id,
                metric_type=metric_type,
                metric_date=metric_date,
                value=value,
                occurred_at=occurred_at,
                correlation_id=(
                    context.correlation_id if context is not None else None
                ),
            )
        )


class StoreAnalyticsService:
    def __init__(
        self,
        stores: StoreRepository,
        analytics: StoreAnalyticsRepository,
        sources: StoreAnalyticsSourceRepository,
        audit: StoreAnalyticsAuditService,
    ) -> None:
        self._stores = stores
        self._analytics = analytics
        self._sources = sources
        self._audit = audit

    async def record_event(
        self,
        *,
        store_id: UUID,
        metric_type: MetricType,
        occurred_at: datetime,
        metadata: Mapping[str, JsonValue] | None = None,
        event_id: UUID | None = None,
    ) -> MetricEvent | None:
        instant = _aware_utc(occurred_at)
        safe_metadata = _metadata(metadata or {})
        recorded = await self._analytics.record_event(
            event_id=event_id or uuid7(),
            store_id=store_id,
            event_type=metric_type,
            occurred_at=instant,
            metadata=safe_metadata,
        )
        if recorded is None:
            return None

        increments: dict[str, int] = {}
        field = _INCREMENT_FIELDS.get(metric_type)
        if field is not None:
            increments[field] = 1
        storage_bytes = None
        if metric_type in {MetricType.MEDIA_UPLOAD, MetricType.MEDIA_DELETED}:
            storage_bytes = await self._sources.active_storage_bytes(store_id)
        active_members = None
        if metric_type in {
            MetricType.STAFF_INVITATION,
            MetricType.STAFF_ACCEPTANCE,
        }:
            active_members = await self._sources.active_members(store_id)

        daily, created = await self._analytics.apply_daily(
            store_id=store_id,
            metric_date=instant.date(),
            increments=increments,
            storage_bytes=storage_bytes,
            active_members=active_members,
        )
        value = _metric_value(daily, metric_type)
        await self._audit.publish(
            StoreMetricRecorded,
            store_id=store_id,
            metric_type=metric_type,
            metric_date=daily.metric_date,
            value=value,
            occurred_at=instant,
        )
        await self._audit.publish(
            DailyMetricsCreated if created else StoreAnalyticsUpdated,
            store_id=store_id,
            metric_type=metric_type,
            metric_date=daily.metric_date,
            value=value,
            occurred_at=instant,
        )
        STORE_METRIC_EVENTS.inc()
        STORE_DAILY_UPDATES.inc()
        if metric_type is MetricType.PROFILE_VIEW:
            STORE_PROFILE_VIEWS.inc()
        if storage_bytes is not None:
            STORE_STORAGE_BYTES.set(storage_bytes)
        return recorded

    async def refresh_active_members(
        self,
        store_id: UUID,
        *,
        occurred_at: datetime,
    ) -> DailyMetrics:
        instant = _aware_utc(occurred_at)
        daily, _ = await self._analytics.apply_daily(
            store_id=store_id,
            metric_date=instant.date(),
            increments={},
            storage_bytes=None,
            active_members=await self._sources.active_members(store_id),
        )
        STORE_DAILY_UPDATES.inc()
        return daily

    async def analytics(
        self,
        store_id: UUID,
        actor_user_id: UUID,
        period: AnalyticsPeriod,
        *,
        offset: int,
        limit: int,
        admin_access: bool = False,
    ) -> StoreAnalytics:
        await self._accessible_store(store_id, actor_user_id, admin_access)
        _period(period)
        daily, total = await self._analytics.list_daily(
            store_id,
            date_from=period.date_from,
            date_to=period.date_to,
            offset=offset,
            limit=limit,
        )
        summary = await self._analytics.summarize(
            store_id,
            date_from=period.date_from,
            date_to=period.date_to,
        )
        return StoreAnalytics(
            store_id=store_id,
            period=period,
            summary=summary,
            daily=tuple(daily),
            total_days=total,
        )

    async def summary(
        self,
        store_id: UUID,
        actor_user_id: UUID,
        period: AnalyticsPeriod,
        *,
        admin_access: bool = False,
    ) -> AnalyticsSummary:
        await self._accessible_store(store_id, actor_user_id, admin_access)
        _period(period)
        return await self._analytics.summarize(
            store_id,
            date_from=period.date_from,
            date_to=period.date_to,
        )

    async def daily(
        self,
        store_id: UUID,
        actor_user_id: UUID,
        period: AnalyticsPeriod,
        *,
        offset: int,
        limit: int,
        admin_access: bool = False,
    ) -> tuple[Sequence[DailyMetrics], int]:
        await self._accessible_store(store_id, actor_user_id, admin_access)
        _period(period)
        return await self._analytics.list_daily(
            store_id,
            date_from=period.date_from,
            date_to=period.date_to,
            offset=offset,
            limit=limit,
        )

    async def storage(
        self,
        store_id: UUID,
        actor_user_id: UUID,
        *,
        admin_access: bool = False,
    ) -> int:
        await self._accessible_store(store_id, actor_user_id, admin_access)
        storage_bytes = await self._sources.active_storage_bytes(store_id)
        STORE_STORAGE_BYTES.set(storage_bytes)
        return storage_bytes

    async def _accessible_store(
        self,
        store_id: UUID,
        actor_user_id: UUID,
        admin_access: bool,
    ) -> None:
        store = (
            await self._stores.get_by_id(store_id)
            if admin_access
            else await self._stores.get_for_owner(store_id, actor_user_id)
        )
        if store is None:
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                title="Store analytics not found",
                detail="The requested Store analytics was not found.",
                status_code=404,
            )


def default_period(today: date | None = None) -> AnalyticsPeriod:
    end = today or datetime.now(UTC).date()
    return AnalyticsPeriod(end - timedelta(days=29), end)


def _period(value: AnalyticsPeriod) -> None:
    if value.date_from > value.date_to:
        raise _validation("date_from", "Start date must not follow end date.")
    if (value.date_to - value.date_from).days > 366:
        raise _validation("date_to", "Analytics periods cannot exceed 367 days.")


def _metadata(value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    if len(value) > 16:
        raise _validation("metadata", "Metric metadata has too many fields.")
    for key in value:
        normalized = key.casefold()
        if any(part in normalized for part in _SENSITIVE_METADATA_PARTS):
            raise _validation(
                "metadata", "Metric metadata contains a prohibited field."
            )
    result = dict(value)
    if len(json.dumps(result, separators=(",", ":"))) > 2048:
        raise _validation("metadata", "Metric metadata is too large.")
    return result


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise _validation("occurred_at", "Metric timestamps must be timezone-aware.")
    return value.astimezone(UTC)


def _metric_value(daily: DailyMetrics, metric_type: MetricType) -> int:
    field = _INCREMENT_FIELDS.get(metric_type)
    if field is not None:
        return int(getattr(daily, field))
    return daily.storage_bytes


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Store analytics validation failed",
        detail="One or more Store analytics fields are invalid.",
        status_code=422,
        errors=[
            FieldError(field=field, code="invalid_store_analytics", message=message)
        ],
    )
