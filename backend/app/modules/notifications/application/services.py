from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from app.common.errors import ErrorCode
from app.common.exceptions import AppError
from app.modules.notifications.application.repositories import (
    DeliveryRepository,
    NotificationOutboxRepository,
    NotificationRepository,
    PreferenceRepository,
    TemplateRepository,
)
from app.modules.notifications.application.schemas import (
    NotificationFilter,
    PreferenceUpdate,
    TestNotification,
)
from app.modules.notifications.domain import (
    Notification,
    NotificationCreated,
    NotificationPreference,
    NotificationRead,
    NotificationSent,
    NotificationStatus,
)
from app.modules.notifications.gateways import NotificationGateway


class NotificationService:
    def __init__(
        self,
        notifications: NotificationRepository,
        preferences: PreferenceRepository,
        templates: TemplateRepository,
        outbox: NotificationOutboxRepository,
    ) -> None:
        self._notifications = notifications
        self._preferences = preferences
        self._templates = templates
        self._outbox = outbox

    async def list(
        self, customer_id: UUID, filters: NotificationFilter
    ) -> tuple[Sequence[Notification], int]:
        return await self._notifications.list_for_customer(customer_id, filters)

    async def detail(self, notification_id: UUID, customer_id: UUID) -> Notification:
        value = await self._notifications.get_for_customer(notification_id, customer_id)
        if value is None:
            raise _not_found()
        return value

    async def mark_read(
        self, notification_id: UUID, customer_id: UUID, expected_version: int
    ) -> Notification:
        value = await self._notifications.get_for_customer(
            notification_id, customer_id, for_update=True
        )
        if value is None:
            raise _not_found()
        if value.version != expected_version:
            raise _conflict()
        if value.read_at is not None:
            return value
        updated = await self._notifications.transition(
            value.id,
            value.version,
            {"read_at": datetime.now(UTC), "updated_by_id": customer_id},
        )
        if updated is None:
            raise _conflict()
        await self._outbox.add(
            NotificationRead(
                notification_id=updated.id,
                customer_id=updated.customer_id,
                store_id=updated.store_id,
                version=updated.version,
            )
        )
        return updated

    async def preferences(self, customer_id: UUID) -> NotificationPreference:
        value = await self._preferences.get(customer_id)
        return value or await self._preferences.add_default(customer_id, customer_id)

    async def update_preferences(
        self, customer_id: UUID, values: PreferenceUpdate
    ) -> NotificationPreference:
        current = await self._preferences.get(customer_id, for_update=True)
        if current is None:
            current = await self._preferences.add_default(customer_id, customer_id)
        if current.version != values.expected_version:
            raise _conflict()
        updated = await self._preferences.update(
            customer_id,
            current.version,
            {**values.values, "updated_by_id": values.actor_id},
        )
        if updated is None:
            raise _conflict()
        return updated


class NotificationTestService:
    def __init__(
        self,
        notifications: NotificationRepository,
        templates: TemplateRepository,
        deliveries: DeliveryRepository,
        outbox: NotificationOutboxRepository,
        gateway: NotificationGateway,
    ) -> None:
        self._notifications = notifications
        self._templates = templates
        self._deliveries = deliveries
        self._outbox = outbox
        self._gateway = gateway

    async def send(self, customer_id: UUID, values: TestNotification) -> Notification:
        template = await self._templates.get_for_event(
            "notification.test", values.channel, "en"
        )
        if template is None:
            raise _not_found()
        now = datetime.now(UTC)
        notification = await self._notifications.add(
            {
                "customer_id": customer_id,
                "store_id": None,
                "template_id": template.id,
                "source_event_id": None,
                "event_name": "notification.test",
                "channel": values.channel,
                "status": NotificationStatus.SENDING,
                "subject": values.subject,
                "body": values.body,
                "variables": {},
                "attempt_count": 1,
                "max_retries": 0,
                "sending_at": now,
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        await self._outbox.add(
            NotificationCreated(
                notification_id=notification.id,
                customer_id=customer_id,
                store_id=None,
                version=notification.version,
            )
        )
        key = f"{notification.id}:{notification.channel.value}"
        if notification.channel.value == "email":
            result = await self._gateway.send_email(
                str(customer_id), notification.subject, notification.body, key
            )
        elif notification.channel.value == "sms":
            result = await self._gateway.send_sms(
                str(customer_id), notification.body, key
            )
        elif notification.channel.value == "push":
            result = await self._gateway.send_push(
                str(customer_id), notification.subject, notification.body, key
            )
        else:
            result = await self._gateway.send_in_app(
                str(customer_id), notification.subject, notification.body, key
            )
        if not result.delivered:
            raise AppError(
                code=ErrorCode.DATABASE_ERROR,
                detail="The Null gateway rejected the test notification.",
                status_code=503,
            )
        await self._deliveries.add(
            {
                "notification_id": notification.id,
                "channel": notification.channel,
                "gateway_reference": result.reference,
                "duration_ms": 0,
                "delivered_at": now,
                "created_by_id": values.actor_id,
                "updated_by_id": values.actor_id,
            }
        )
        delivered = await self._notifications.transition(
            notification.id,
            notification.version,
            {"status": NotificationStatus.DELIVERED, "delivered_at": now},
        )
        if delivered is None:
            raise _conflict()
        await self._outbox.add(
            NotificationSent(
                notification_id=delivered.id,
                customer_id=customer_id,
                store_id=None,
                version=delivered.version,
            )
        )
        return delivered


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        detail="The requested Notification was not found.",
        status_code=404,
        title="Notification not found",
    )


def _conflict() -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        detail="The Notification was modified by another request.",
        status_code=409,
        title="Notification conflict",
    )
