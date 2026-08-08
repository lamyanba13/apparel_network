from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID

from app.modules.notifications.application.repositories import (
    DeliveryRepository,
    NotificationOutboxRepository,
    NotificationRepository,
    PreferenceRepository,
    TemplateRepository,
)
from app.modules.notifications.domain import (
    Notification,
    NotificationChannel,
    NotificationCreated,
    NotificationFailed,
    NotificationSent,
    NotificationStatus,
)
from app.modules.notifications.gateways import GatewayResult, NotificationGateway
from app.modules.notifications.templates import render_template
from app.observability.metrics import (
    NOTIFICATION_DELIVERY_DURATION,
    NOTIFICATIONS_CREATED,
    NOTIFICATIONS_FAILED,
    NOTIFICATIONS_RETRIED,
    NOTIFICATIONS_SENT,
    OUTBOX_EVENT_PROCESSING_DURATION,
)

logger = logging.getLogger(__name__)

SUPPORTED_COMMERCE_EVENTS = (
    "order.created",
    "order.confirmed",
    "payment.created",
    "payment.captured",
    "shipment.created",
    "shipment.packed",
    "shipment.shipped",
    "shipment.delivered",
    "return.approved",
    "refund.completed",
    "promotion.applied",
    "coupon.redeemed",
)


class NotificationDispatcher:
    def __init__(
        self,
        notifications: NotificationRepository,
        preferences: PreferenceRepository,
        templates: TemplateRepository,
        deliveries: DeliveryRepository,
        outbox: NotificationOutboxRepository,
        gateway: NotificationGateway,
        *,
        max_retries: int = 3,
        retry_base_seconds: int = 60,
    ) -> None:
        self._notifications = notifications
        self._preferences = preferences
        self._templates = templates
        self._deliveries = deliveries
        self._outbox = outbox
        self._gateway = gateway
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds

    async def dispatch_pending(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> int:
        at = now or datetime.now(UTC)
        count = 0
        for event_id, event_name, payload in await self._outbox.pending(
            SUPPORTED_COMMERCE_EVENTS, limit, now=at
        ):
            started = perf_counter()
            try:
                attempted, waiting = await self._dispatch_event(
                    event_id, event_name, payload, at
                )
                count += attempted
                if waiting:
                    await self._outbox.release(event_id, at)
                else:
                    await self._outbox.mark_published(event_id, at)
            except Exception as error:
                logger.exception(
                    "commerce_event_processing_failed",
                    extra={
                        "event": "commerce_event_processing_failed",
                        "event_id": str(event_id),
                        "source_event_name": event_name,
                    },
                )
                await self._outbox.mark_failed(event_id, at, str(error))
            finally:
                OUTBOX_EVENT_PROCESSING_DURATION.observe(perf_counter() - started)
        return count

    async def _dispatch_event(
        self,
        event_id: UUID,
        event_name: str,
        payload: dict[str, object],
        at: datetime,
    ) -> tuple[int, bool]:
        customer_id = _uuid(payload.get("customer_id"))
        if customer_id is None:
            return 0, False
        store_id = _uuid(payload.get("store_id"))
        preference = await self._preferences.get(
            customer_id
        ) or await self._preferences.add_default(customer_id)
        waiting = False
        count = 0
        for channel in NotificationChannel:
            notification = await self._notifications.get_by_source(
                event_id, customer_id, channel, for_update=True
            )
            if notification is None:
                template = await self._templates.get_for_event(
                    event_name, channel, preference.language
                )
                if template is None:
                    continue
                variables = {
                    key: value
                    for key, value in payload.items()
                    if isinstance(value, (str, int, float, bool)) or value is None
                }
                notification = await self._notifications.add(
                    {
                        "customer_id": customer_id,
                        "store_id": store_id,
                        "template_id": template.id,
                        "source_event_id": event_id,
                        "event_name": event_name,
                        "channel": channel,
                        "status": NotificationStatus.PENDING,
                        "subject": render_template(template.subject, variables),
                        "body": render_template(template.body, variables),
                        "variables": variables,
                        "attempt_count": 0,
                        "max_retries": self._max_retries,
                    }
                )
                NOTIFICATIONS_CREATED.labels(channel.value).inc()
                await self._outbox.add(
                    NotificationCreated(
                        notification_id=notification.id,
                        customer_id=customer_id,
                        store_id=store_id,
                        version=notification.version,
                    )
                )
            if not preference.channel_enabled(channel, transactional=True):
                if notification.status not in _TERMINAL:
                    await self._notifications.transition(
                        notification.id,
                        notification.version,
                        {
                            "status": NotificationStatus.CANCELLED,
                            "cancelled_at": at,
                            "deleted_at": at,
                        },
                    )
                continue
            if notification.status in _TERMINAL:
                continue
            if (
                notification.next_retry_at is not None
                and notification.next_retry_at > at
            ):
                waiting = True
                continue
            delivered = await self._send(notification, customer_id, at)
            waiting = waiting or not delivered
            count += 1
        return count, waiting

    async def _send(self, value: Notification, customer_id: UUID, at: datetime) -> bool:
        current = value
        if current.status in {NotificationStatus.PENDING, NotificationStatus.RETRYING}:
            queued = await self._notifications.transition(
                current.id,
                current.version,
                {
                    "status": NotificationStatus.QUEUED,
                    "queued_at": at,
                    "next_retry_at": None,
                },
            )
            if queued is None:
                return True
            current = queued
        sending = await self._notifications.transition(
            current.id,
            current.version,
            {
                "status": NotificationStatus.SENDING,
                "sending_at": at,
                "attempt_count": current.attempt_count + 1,
            },
        )
        if sending is None:
            return True
        started = perf_counter()
        result = await self._invoke(sending, str(customer_id))
        duration_ms = max(0, round((perf_counter() - started) * 1000))
        NOTIFICATION_DELIVERY_DURATION.labels(sending.channel.value).observe(
            duration_ms / 1000
        )
        if result.delivered:
            if not await self._deliveries.exists(sending.id):
                await self._deliveries.add(
                    {
                        "notification_id": sending.id,
                        "channel": sending.channel,
                        "gateway_reference": result.reference,
                        "duration_ms": duration_ms,
                        "delivered_at": at,
                    }
                )
            delivered = await self._notifications.transition(
                sending.id,
                sending.version,
                {"status": NotificationStatus.DELIVERED, "delivered_at": at},
            )
            if delivered is not None:
                NOTIFICATIONS_SENT.labels(sending.channel.value).inc()
                await self._outbox.add(
                    NotificationSent(
                        notification_id=delivered.id,
                        customer_id=delivered.customer_id,
                        store_id=delivered.store_id,
                        version=delivered.version,
                    )
                )
            return True
        retrying = sending.attempt_count <= sending.max_retries
        retry_at = (
            at
            + timedelta(
                seconds=self._retry_base_seconds * (2 ** (sending.attempt_count - 1))
            )
            if retrying
            else None
        )
        await self._deliveries.add_failure(
            {
                "notification_id": sending.id,
                "attempt": sending.attempt_count,
                "error_code": result.error_code or "delivery_failed",
                "error_detail": result.error_detail
                or "The gateway rejected the notification.",
                "retry_at": retry_at,
                "occurred_at": at,
            }
        )
        failed = await self._notifications.transition(
            sending.id,
            sending.version,
            {
                "status": (
                    NotificationStatus.RETRYING
                    if retrying
                    else NotificationStatus.FAILED
                ),
                "next_retry_at": retry_at,
                "failed_at": None if retrying else at,
            },
        )
        if retrying:
            NOTIFICATIONS_RETRIED.labels(sending.channel.value).inc()
            return False
        NOTIFICATIONS_FAILED.labels(sending.channel.value).inc()
        if failed is not None:
            await self._outbox.add(
                NotificationFailed(
                    notification_id=failed.id,
                    customer_id=failed.customer_id,
                    store_id=failed.store_id,
                    version=failed.version,
                )
            )
        return True

    async def _invoke(self, value: Notification, recipient: str) -> GatewayResult:
        key = f"{value.id}:{value.channel.value}"
        if value.channel == NotificationChannel.EMAIL:
            return await self._gateway.send_email(
                recipient, value.subject, value.body, key
            )
        if value.channel == NotificationChannel.SMS:
            return await self._gateway.send_sms(recipient, value.body, key)
        if value.channel == NotificationChannel.PUSH:
            return await self._gateway.send_push(
                recipient, value.subject, value.body, key
            )
        return await self._gateway.send_in_app(
            recipient, value.subject, value.body, key
        )


_TERMINAL = {
    NotificationStatus.DELIVERED,
    NotificationStatus.FAILED,
    NotificationStatus.CANCELLED,
}


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value is not None else None
    except ValueError:
        return None
