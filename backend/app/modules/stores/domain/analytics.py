from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import JsonValue

type MetricMetadata = dict[str, JsonValue]


class MetricType(StrEnum):
    PROFILE_VIEW = "profile_view"
    GALLERY_VIEW = "gallery_view"
    MEDIA_UPLOAD = "media_upload"
    MEDIA_DELETED = "media_deleted"
    STAFF_INVITATION = "staff_invitation"
    STAFF_ACCEPTANCE = "staff_acceptance"
    VERIFICATION_SUBMISSION = "verification_submission"
    VERIFICATION_APPROVAL = "verification_approval"
    VERIFICATION_REJECTION = "verification_rejection"


@dataclass(frozen=True, slots=True)
class DailyMetrics:
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


@dataclass(frozen=True, slots=True)
class MetricEvent:
    id: UUID
    store_id: UUID
    event_type: MetricType
    occurred_at: datetime
    metadata: MetricMetadata
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AnalyticsPeriod:
    date_from: date
    date_to: date


@dataclass(frozen=True, slots=True)
class AnalyticsSummary:
    store_id: UUID
    period: AnalyticsPeriod
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


@dataclass(frozen=True, slots=True)
class StoreAnalytics:
    store_id: UUID
    period: AnalyticsPeriod
    summary: AnalyticsSummary
    daily: tuple[DailyMetrics, ...]
    total_days: int
