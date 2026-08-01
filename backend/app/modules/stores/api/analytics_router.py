from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query

from app.common.pagination import PageMetadata
from app.modules.identity.api.authorization import (
    AuthorizationServiceDependency,
    require_any_permission,
)
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.identity.domain.authorization import AuthorizationPrincipal
from app.modules.stores.api.analytics_schemas import (
    AnalyticsPeriodResponse,
    AnalyticsSummaryResponse,
    DailyMetricsListResponse,
    DailyMetricsResponse,
    StoreAnalyticsResponse,
    StoreStorageResponse,
)
from app.modules.stores.api.dependencies import StoreAnalyticsServiceDependency
from app.modules.stores.domain.analytics import (
    AnalyticsPeriod,
    AnalyticsSummary,
    DailyMetrics,
)

router = APIRouter(
    prefix="/stores/{store_id}/analytics",
    tags=["Store Analytics"],
)

_AUTHORIZATION = [require_any_permission("store:view", "admin:access")]
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks Store analytics access"},
    404: {"description": "Store analytics not found or concealed"},
    422: {"description": "Date range or pagination validation failed"},
}


def _period(date_from: date | None, date_to: date | None) -> AnalyticsPeriod:
    end = date_to or datetime.now(UTC).date()
    start = date_from or end - timedelta(days=29)
    return AnalyticsPeriod(start, end)


def _daily(value: DailyMetrics) -> DailyMetricsResponse:
    return DailyMetricsResponse(
        id=value.id,
        store_id=value.store_id,
        metric_date=value.metric_date,
        profile_views=value.profile_views,
        gallery_views=value.gallery_views,
        media_uploads=value.media_uploads,
        staff_invitations=value.staff_invitations,
        staff_acceptances=value.staff_acceptances,
        verification_submissions=value.verification_submissions,
        verification_approvals=value.verification_approvals,
        verification_rejections=value.verification_rejections,
        storage_bytes=value.storage_bytes,
        active_members=value.active_members,
        created_at=value.created_at,
        updated_at=value.updated_at,
        version=value.version,
    )


def _summary(value: AnalyticsSummary) -> AnalyticsSummaryResponse:
    return AnalyticsSummaryResponse(
        store_id=value.store_id,
        period=AnalyticsPeriodResponse(
            date_from=value.period.date_from,
            date_to=value.period.date_to,
        ),
        profile_views=value.profile_views,
        gallery_views=value.gallery_views,
        media_uploads=value.media_uploads,
        staff_invitations=value.staff_invitations,
        staff_acceptances=value.staff_acceptances,
        verification_submissions=value.verification_submissions,
        verification_approvals=value.verification_approvals,
        verification_rejections=value.verification_rejections,
        storage_bytes=value.storage_bytes,
        active_members=value.active_members,
    )


async def _is_admin(
    identity: CurrentIdentity,
    authorization: AuthorizationServiceDependency,
) -> bool:
    return await authorization.has_permission(
        AuthorizationPrincipal(
            user_id=identity.user.id,
            session_id=identity.session.id,
        ),
        "admin:access",
    )


@router.get(
    "",
    response_model=StoreAnalyticsResponse,
    summary="Get Store operational analytics",
    description=(
        "Returns an owner- or administrator-scoped operational summary and a "
        "bounded page of UTC daily metrics for the selected inclusive period."
    ),
    dependencies=_AUTHORIZATION,
    responses=_RESPONSES,
)
async def get_store_analytics(
    store_id: UUID,
    identity: CurrentIdentity,
    authorization: AuthorizationServiceDependency,
    service: StoreAnalyticsServiceDependency,
    date_from: date | None = None,
    date_to: date | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> StoreAnalyticsResponse:
    period = _period(date_from, date_to)
    value = await service.analytics(
        store_id,
        identity.user.id,
        period,
        offset=offset,
        limit=limit,
        admin_access=await _is_admin(identity, authorization),
    )
    items = [_daily(item) for item in value.daily]
    return StoreAnalyticsResponse(
        store_id=value.store_id,
        period=AnalyticsPeriodResponse(
            date_from=value.period.date_from,
            date_to=value.period.date_to,
        ),
        summary=_summary(value.summary),
        daily=DailyMetricsListResponse(
            items=items,
            page=PageMetadata(
                has_more=offset + len(items) < value.total_days,
                limit=limit,
                total=value.total_days,
                offset=offset,
            ),
        ),
    )


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Summarize Store operational metrics",
    description=(
        "Aggregates daily operational counters for an inclusive UTC date range."
    ),
    dependencies=_AUTHORIZATION,
    responses=_RESPONSES,
)
async def get_store_analytics_summary(
    store_id: UUID,
    identity: CurrentIdentity,
    authorization: AuthorizationServiceDependency,
    service: StoreAnalyticsServiceDependency,
    date_from: date | None = None,
    date_to: date | None = None,
) -> AnalyticsSummaryResponse:
    return _summary(
        await service.summary(
            store_id,
            identity.user.id,
            _period(date_from, date_to),
            admin_access=await _is_admin(identity, authorization),
        )
    )


@router.get(
    "/daily",
    response_model=DailyMetricsListResponse,
    summary="List Store daily operational metrics",
    description=(
        "Returns a bounded newest-first page within an inclusive UTC date range."
    ),
    dependencies=_AUTHORIZATION,
    responses=_RESPONSES,
)
async def list_store_daily_metrics(
    store_id: UUID,
    identity: CurrentIdentity,
    authorization: AuthorizationServiceDependency,
    service: StoreAnalyticsServiceDependency,
    date_from: date | None = None,
    date_to: date | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DailyMetricsListResponse:
    values, total = await service.daily(
        store_id,
        identity.user.id,
        _period(date_from, date_to),
        offset=offset,
        limit=limit,
        admin_access=await _is_admin(identity, authorization),
    )
    items = [_daily(item) for item in values]
    return DailyMetricsListResponse(
        items=items,
        page=PageMetadata(
            has_more=offset + len(items) < total,
            limit=limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/storage",
    response_model=StoreStorageResponse,
    summary="Get current active Store media storage",
    description=(
        "Calculates authoritative bytes for active, non-deleted Store media. "
        "Archived and soft-deleted media are excluded."
    ),
    dependencies=_AUTHORIZATION,
    responses=_RESPONSES,
)
async def get_store_storage(
    store_id: UUID,
    identity: CurrentIdentity,
    authorization: AuthorizationServiceDependency,
    service: StoreAnalyticsServiceDependency,
) -> StoreStorageResponse:
    measured_at = datetime.now(UTC)
    return StoreStorageResponse(
        store_id=store_id,
        storage_bytes=await service.storage(
            store_id,
            identity.user.id,
            admin_access=await _is_admin(identity, authorization),
        ),
        measured_at=measured_at,
    )
