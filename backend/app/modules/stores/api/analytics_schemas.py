from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.common.pagination import PageMetadata


class AnalyticsPeriodResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date
    date_to: date


class DailyMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    store_id: UUID
    metric_date: date
    profile_views: int
    gallery_views: int
    media_uploads: int
    staff_invitations: int
    staff_acceptances: int
    verification_submissions: int
    verification_approvals: int
    verification_rejections: int
    storage_bytes: int
    active_members: int
    created_at: datetime
    updated_at: datetime
    version: int


class AnalyticsSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: UUID
    period: AnalyticsPeriodResponse
    profile_views: int
    gallery_views: int
    media_uploads: int
    staff_invitations: int
    staff_acceptances: int
    verification_submissions: int
    verification_approvals: int
    verification_rejections: int
    storage_bytes: int
    active_members: int


class DailyMetricsListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DailyMetricsResponse]
    page: PageMetadata


class StoreAnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: UUID
    period: AnalyticsPeriodResponse
    summary: AnalyticsSummaryResponse
    daily: DailyMetricsListResponse


class StoreStorageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: UUID
    storage_bytes: int
    measured_at: datetime
