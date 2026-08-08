from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.events.infrastructure.repositories import SqlAlchemyReliableOutboxRepository
from app.modules.notifications.application.schemas import NotificationFilter
from app.modules.notifications.domain import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationTemplate,
)
from app.modules.notifications.domain.events import NotificationEvent
from app.modules.notifications.infrastructure.models import (
    NotificationDeliveryModel,
    NotificationFailureModel,
    NotificationModel,
    NotificationPreferenceModel,
    NotificationTemplateModel,
)
from app.modules.products.domain import OutboxStatus
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.observability.metrics import OUTBOX_EVENTS_CREATED


class SqlAlchemyNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, values: Mapping[str, object]) -> Notification:
        model = NotificationModel(**dict(values))
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _notification(model)

    async def get_for_customer(
        self, notification_id: UUID, customer_id: UUID, *, for_update: bool = False
    ) -> Notification | None:
        query = select(NotificationModel).where(
            NotificationModel.id == notification_id,
            NotificationModel.customer_id == customer_id,
            NotificationModel.deleted_at.is_(None),
        )
        if for_update:
            query = query.with_for_update()
        model = await self._session.scalar(query)
        return _notification(model) if model else None

    async def get_by_source(
        self,
        source_event_id: UUID,
        customer_id: UUID,
        channel: NotificationChannel,
        *,
        for_update: bool = False,
    ) -> Notification | None:
        query = select(NotificationModel).where(
            NotificationModel.source_event_id == source_event_id,
            NotificationModel.customer_id == customer_id,
            NotificationModel.channel == channel,
        )
        if for_update:
            query = query.with_for_update()
        model = await self._session.scalar(query)
        return _notification(model) if model else None

    async def list_for_customer(
        self, customer_id: UUID, filters: NotificationFilter
    ) -> tuple[Sequence[Notification], int]:
        query = select(NotificationModel).where(
            NotificationModel.customer_id == customer_id,
            NotificationModel.deleted_at.is_(None),
        )
        if filters.status:
            query = query.where(NotificationModel.status == filters.status)
        if filters.channel:
            query = query.where(NotificationModel.channel == filters.channel)
        if filters.unread_only:
            query = query.where(NotificationModel.read_at.is_(None))
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                query.order_by(
                    NotificationModel.created_at.desc(), NotificationModel.id
                )
                .offset(filters.offset)
                .limit(filters.limit)
            )
        ).all()
        return [_notification(row) for row in rows], total

    async def transition(
        self, notification_id: UUID, expected_version: int, values: Mapping[str, object]
    ) -> Notification | None:
        result = await self._session.execute(
            update(NotificationModel)
            .where(
                NotificationModel.id == notification_id,
                NotificationModel.version == expected_version,
            )
            .values(
                **dict(values),
                version=NotificationModel.version + 1,
                updated_at=func.now(),
            )
            .returning(NotificationModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _notification(model) if model else None


class SqlAlchemyPreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, customer_id: UUID, *, for_update: bool = False
    ) -> NotificationPreference | None:
        query = select(NotificationPreferenceModel).where(
            NotificationPreferenceModel.customer_id == customer_id,
            NotificationPreferenceModel.deleted_at.is_(None),
        )
        if for_update:
            query = query.with_for_update()
        model = await self._session.scalar(query)
        return _preference(model) if model else None

    async def add_default(
        self, customer_id: UUID, actor_id: UUID | None = None
    ) -> NotificationPreference:
        model = NotificationPreferenceModel(
            customer_id=customer_id, created_by_id=actor_id, updated_by_id=actor_id
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _preference(model)

    async def update(
        self, customer_id: UUID, expected_version: int, values: Mapping[str, object]
    ) -> NotificationPreference | None:
        result = await self._session.execute(
            update(NotificationPreferenceModel)
            .where(
                NotificationPreferenceModel.customer_id == customer_id,
                NotificationPreferenceModel.version == expected_version,
                NotificationPreferenceModel.deleted_at.is_(None),
            )
            .values(
                **dict(values),
                version=NotificationPreferenceModel.version + 1,
                updated_at=func.now(),
            )
            .returning(NotificationPreferenceModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _preference(model) if model else None


class SqlAlchemyTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_event(
        self, event_name: str, channel: NotificationChannel, language: str
    ) -> NotificationTemplate | None:
        model = await self._session.scalar(
            select(NotificationTemplateModel)
            .where(
                NotificationTemplateModel.event_name == event_name,
                NotificationTemplateModel.channel == channel,
                NotificationTemplateModel.language.in_((language, "en")),
                NotificationTemplateModel.active.is_(True),
                NotificationTemplateModel.deleted_at.is_(None),
            )
            .order_by((NotificationTemplateModel.language == language).desc())
            .limit(1)
        )
        return _template(model) if model else None


class SqlAlchemyDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists(self, notification_id: UUID) -> bool:
        return (
            await self._session.scalar(
                select(NotificationDeliveryModel.id).where(
                    NotificationDeliveryModel.notification_id == notification_id
                )
            )
            is not None
        )

    async def add(self, values: Mapping[str, object]) -> None:
        self._session.add(NotificationDeliveryModel(**dict(values)))
        await self._session.flush()

    async def add_failure(self, values: Mapping[str, object]) -> None:
        self._session.add(NotificationFailureModel(**dict(values)))
        await self._session.flush()


class SqlAlchemyNotificationOutboxRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        worker_id: str | None = None,
        lease_seconds: int = 300,
        max_attempts: int = 5,
        retry_base_seconds: int = 30,
    ) -> None:
        self._session = session
        self._worker_id = worker_id or f"notifications:{uuid7()}"
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds
        self._reliable = SqlAlchemyReliableOutboxRepository(
            session, consumer_name="notifications"
        )

    async def pending(
        self,
        event_names: Sequence[str],
        limit: int,
        *,
        now: datetime | None = None,
    ) -> Sequence[tuple[UUID, str, dict[str, object]]]:
        claims = await self._reliable.claim(
            event_names,
            worker_id=self._worker_id,
            now=now or datetime.now(UTC),
            lease_timeout=timedelta(seconds=self._lease_seconds),
            limit=limit,
        )
        return [(claim.id, claim.event_name, claim.payload) for claim in claims]

    async def mark_published(self, event_id: UUID, at: datetime) -> None:
        await self._reliable.mark_processed(event_id, worker_id=self._worker_id, now=at)

    async def release(self, event_id: UUID, at: datetime) -> None:
        await self._reliable.release(event_id, worker_id=self._worker_id, now=at)

    async def mark_failed(self, event_id: UUID, at: datetime, error: str) -> None:
        await self._reliable.mark_failed(
            event_id,
            worker_id=self._worker_id,
            now=at,
            error=error,
            max_attempts=self._max_attempts,
            retry_base_seconds=self._retry_base_seconds,
        )

    async def add(self, event: NotificationEvent) -> None:
        self._session.add(
            EventOutboxModel(
                id=event.event_id,
                aggregate_type="notification",
                aggregate_id=event.notification_id,
                event_name=event.event_name,
                payload=event.payload,
                occurred_at=event.occurred_at,
                available_at=event.occurred_at,
                status=OutboxStatus.PENDING,
                retry_count=0,
            )
        )
        await self._session.flush()
        OUTBOX_EVENTS_CREATED.inc()


def _notification(model: NotificationModel) -> Notification:
    return Notification(
        id=model.id,
        customer_id=model.customer_id,
        store_id=model.store_id,
        template_id=model.template_id,
        source_event_id=model.source_event_id,
        event_name=model.event_name,
        channel=model.channel,
        status=model.status,
        subject=model.subject,
        body=model.body,
        variables=cast(dict[str, JsonValue], model.variables),
        attempt_count=model.attempt_count,
        max_retries=model.max_retries,
        next_retry_at=model.next_retry_at,
        queued_at=model.queued_at,
        sending_at=model.sending_at,
        delivered_at=model.delivered_at,
        failed_at=model.failed_at,
        cancelled_at=model.cancelled_at,
        read_at=model.read_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


def _preference(model: NotificationPreferenceModel) -> NotificationPreference:
    return NotificationPreference(
        id=model.id,
        customer_id=model.customer_id,
        email_enabled=model.email_enabled,
        sms_enabled=model.sms_enabled,
        push_enabled=model.push_enabled,
        in_app_enabled=model.in_app_enabled,
        language=model.language,
        marketing_opt_in=model.marketing_opt_in,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _template(model: NotificationTemplateModel) -> NotificationTemplate:
    return NotificationTemplate(
        id=model.id,
        key=model.key,
        event_name=model.event_name,
        channel=model.channel,
        language=model.language,
        subject=model.subject,
        body=model.body,
        variables=tuple(model.variables),
        active=model.active,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
