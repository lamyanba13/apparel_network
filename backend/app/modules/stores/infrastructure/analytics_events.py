from __future__ import annotations

from app.common.events import DomainEvent, EventPublisher
from app.modules.stores.application.analytics_services import StoreAnalyticsService
from app.modules.stores.domain.analytics import MetricType

_EVENT_METRICS = {
    "store.verification.submitted": MetricType.VERIFICATION_SUBMISSION,
    "store.verified": MetricType.VERIFICATION_APPROVAL,
    "store.verification.rejected": MetricType.VERIFICATION_REJECTION,
    "store.member.invited": MetricType.STAFF_INVITATION,
    "store.member.accepted": MetricType.STAFF_ACCEPTANCE,
    "store.logo.uploaded": MetricType.MEDIA_UPLOAD,
    "store.banner.uploaded": MetricType.MEDIA_UPLOAD,
    "store.gallery.uploaded": MetricType.MEDIA_UPLOAD,
    "store.media.deleted": MetricType.MEDIA_DELETED,
}
_MEMBERSHIP_SNAPSHOT_EVENTS = {
    "store.member.declined",
    "store.member.suspended",
    "store.member.reactivated",
    "store.member.removed",
}


class StoreAnalyticsEventPublisher(EventPublisher):
    """Project existing Store events into analytics in the request transaction."""

    def __init__(
        self,
        delegate: EventPublisher,
        analytics: StoreAnalyticsService,
    ) -> None:
        self._delegate = delegate
        self._analytics = analytics

    async def publish(self, event: DomainEvent) -> None:
        await self._delegate.publish(event)
        store_id = event.payload.get("store_id")
        if not isinstance(store_id, str):
            return
        from uuid import UUID

        parsed_store_id = UUID(store_id)
        metric_type = _EVENT_METRICS.get(event.event_name)
        if metric_type is not None:
            await self._analytics.record_event(
                store_id=parsed_store_id,
                metric_type=metric_type,
                occurred_at=event.occurred_at,
                metadata={"source_event": event.event_name},
                event_id=event.event_id,
            )
        elif event.event_name in _MEMBERSHIP_SNAPSHOT_EVENTS:
            await self._analytics.refresh_active_members(
                parsed_store_id,
                occurred_at=event.occurred_at,
            )
