from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.domain import ClaimedEvent, OutboxInspection
from app.events.infrastructure.models import EventConsumerReceiptModel
from app.modules.products.domain import OutboxStatus
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.observability.metrics import (
    OUTBOX_EVENTS_CLAIMED,
    OUTBOX_EVENTS_FAILED,
    OUTBOX_EVENTS_PERMANENTLY_FAILED,
    OUTBOX_EVENTS_PROCESSED,
    OUTBOX_EVENTS_RECOVERED,
    OUTBOX_EVENTS_RETRIED,
)


class SqlAlchemyReliableOutboxRepository:
    def __init__(
        self, session: AsyncSession, *, consumer_name: str = "commerce-events"
    ) -> None:
        self._session = session
        self._consumer_name = consumer_name

    async def claim(
        self,
        event_names: Sequence[str],
        *,
        worker_id: str,
        now: datetime,
        lease_timeout: timedelta,
        limit: int,
    ) -> Sequence[ClaimedEvent]:
        stale_before = now - lease_timeout
        eligible = or_(
            and_(
                EventOutboxModel.status == OutboxStatus.PENDING,
                EventOutboxModel.available_at <= now,
            ),
            and_(
                EventOutboxModel.status == OutboxStatus.PROCESSING,
                EventOutboxModel.locked_at <= stale_before,
            ),
        )
        query = (
            select(EventOutboxModel)
            .where(eligible, EventOutboxModel.event_name.in_(event_names))
            .order_by(EventOutboxModel.available_at, EventOutboxModel.id)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        rows = (await self._session.scalars(query)).all()
        claims: list[ClaimedEvent] = []
        for row in rows:
            recovered = row.status is OutboxStatus.PROCESSING
            row.status = OutboxStatus.PROCESSING
            row.attempts += 1
            row.locked_at = now
            row.locked_by = worker_id
            row.updated_at = now
            claims.append(
                ClaimedEvent(
                    id=row.id,
                    event_name=row.event_name,
                    payload=row.payload,
                    attempts=row.attempts,
                    recovered=recovered,
                )
            )
            OUTBOX_EVENTS_CLAIMED.inc()
            if recovered:
                OUTBOX_EVENTS_RECOVERED.inc()
        await self._session.flush()
        return claims

    async def mark_processed(
        self, event_id: UUID, *, worker_id: str, now: datetime
    ) -> bool:
        row = await self._claimed(event_id, worker_id)
        if row is None:
            return False
        await self._session.execute(
            insert(EventConsumerReceiptModel)
            .values(
                event_id=event_id,
                consumer_name=self._consumer_name,
                processed_at=now,
            )
            .on_conflict_do_nothing(index_elements=["event_id", "consumer_name"])
        )
        row.status = OutboxStatus.PUBLISHED
        row.published_at = now
        row.locked_at = None
        row.locked_by = None
        row.last_error = None
        row.updated_at = now
        row.version += 1
        await self._session.flush()
        OUTBOX_EVENTS_PROCESSED.inc()
        return True

    async def release(self, event_id: UUID, *, worker_id: str, now: datetime) -> bool:
        row = await self._claimed(event_id, worker_id)
        if row is None:
            return False
        row.status = OutboxStatus.PENDING
        row.available_at = now
        row.locked_at = None
        row.locked_by = None
        row.updated_at = now
        row.version += 1
        await self._session.flush()
        OUTBOX_EVENTS_RETRIED.inc()
        return True

    async def mark_failed(
        self,
        event_id: UUID,
        *,
        worker_id: str,
        now: datetime,
        error: str,
        max_attempts: int,
        retry_base_seconds: int,
    ) -> bool:
        row = await self._claimed(event_id, worker_id)
        if row is None:
            return False
        terminal = row.attempts >= max_attempts
        row.status = OutboxStatus.FAILED if terminal else OutboxStatus.PENDING
        row.retry_count = row.attempts
        row.available_at = now + timedelta(
            seconds=retry_base_seconds * (2 ** max(0, row.attempts - 1))
        )
        row.locked_at = None
        row.locked_by = None
        row.last_error = _safe_error(error)
        row.updated_at = now
        row.version += 1
        await self._session.flush()
        OUTBOX_EVENTS_FAILED.inc()
        if terminal:
            OUTBOX_EVENTS_PERMANENTLY_FAILED.inc()
        else:
            OUTBOX_EVENTS_RETRIED.inc()
        return True

    async def inspect_problematic(
        self, *, now: datetime, lease_timeout: timedelta, limit: int
    ) -> Sequence[OutboxInspection]:
        stale_before = now - lease_timeout
        rows = (
            await self._session.scalars(
                select(EventOutboxModel)
                .where(
                    or_(
                        EventOutboxModel.status == OutboxStatus.FAILED,
                        and_(
                            EventOutboxModel.status == OutboxStatus.PROCESSING,
                            EventOutboxModel.locked_at <= stale_before,
                        ),
                    )
                )
                .order_by(EventOutboxModel.updated_at, EventOutboxModel.id)
                .limit(limit)
            )
        ).all()
        return [_inspection(row) for row in rows]

    async def recover(
        self,
        event_id: UUID,
        *,
        now: datetime,
        lease_timeout: timedelta,
    ) -> OutboxInspection | None:
        stale_before = now - lease_timeout
        row = await self._session.scalar(
            select(EventOutboxModel)
            .where(
                EventOutboxModel.id == event_id,
                or_(
                    EventOutboxModel.status == OutboxStatus.FAILED,
                    and_(
                        EventOutboxModel.status == OutboxStatus.PROCESSING,
                        EventOutboxModel.locked_at <= stale_before,
                    ),
                ),
            )
            .with_for_update()
        )
        if row is None:
            return None
        row.status = OutboxStatus.PENDING
        row.available_at = now
        row.locked_at = None
        row.locked_by = None
        row.updated_at = now
        row.version += 1
        await self._session.flush()
        OUTBOX_EVENTS_RECOVERED.inc()
        return _inspection(row)

    async def _claimed(self, event_id: UUID, worker_id: str) -> EventOutboxModel | None:
        row: EventOutboxModel | None = await self._session.scalar(
            select(EventOutboxModel)
            .where(
                EventOutboxModel.id == event_id,
                EventOutboxModel.status == OutboxStatus.PROCESSING,
                EventOutboxModel.locked_by == worker_id,
            )
            .with_for_update()
        )
        return row


def _inspection(row: EventOutboxModel) -> OutboxInspection:
    return OutboxInspection(
        id=row.id,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        event_name=row.event_name,
        occurred_at=row.occurred_at,
        status=row.status,
        available_at=row.available_at,
        attempts=row.attempts,
        locked_at=row.locked_at,
        locked_by=row.locked_by,
        dispatched_at=row.dispatched_at,
        published_at=row.published_at,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _safe_error(value: str) -> str:
    normalized = " ".join(value.split())
    return (normalized or "Event processing failed.")[:2000]
