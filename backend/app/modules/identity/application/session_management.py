from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import ErrorCode
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.identity.application.repositories import RefreshSessionRepository
from app.modules.identity.application.schemas import RefreshSessionRecord
from app.modules.identity.domain.session_events import (
    OtherSessionsRevoked,
    SessionCleanupCompleted,
    SessionExpired,
    SessionRenamed,
    SessionRevoked,
)
from app.observability.metrics import (
    SESSION_ACTIVE,
    SESSION_CLEANUP_EXECUTIONS,
    SESSION_REVOCATIONS,
    SESSION_REVOKED,
)


class AdministrativeSessionService(Protocol):
    """Future administrative boundary; intentionally has no implementation."""

    async def list_for_user(self, user_id: UUID) -> Sequence[RefreshSessionRecord]: ...

    async def revoke_for_user(self, user_id: UUID, session_id: UUID) -> None: ...


class CleanupJob(Protocol):
    """Scheduler-neutral contract implemented by bounded cleanup jobs."""

    async def run(self) -> tuple[int, int]: ...


class SessionManagementService:
    def __init__(
        self,
        db_session: AsyncSession,
        repository: RefreshSessionRepository,
        events: EventPublisher,
    ) -> None:
        self._db_session = db_session
        self._repository = repository
        self._events = events

    async def list_active(self, user_id: UUID) -> Sequence[RefreshSessionRecord]:
        now = datetime.now(UTC)
        records = await self._repository.list_active_for_user(user_id, now=now)
        await self._snapshot_metrics(now)
        return records

    async def current(self, user_id: UUID, session_id: UUID) -> RefreshSessionRecord:
        record = await self._repository.get_for_user(session_id, user_id)
        if (
            record is None
            or record.is_revoked
            or record.expires_at <= datetime.now(UTC)
        ):
            raise _not_found()
        return record

    async def rename(
        self, user_id: UUID, session_id: UUID, display_name: str
    ) -> RefreshSessionRecord:
        existing = await self._repository.get_for_user(session_id, user_id)
        if existing is None:
            raise _not_found()
        if existing.is_revoked:
            raise _conflict("A revoked session cannot be renamed.")
        async with _transaction(self._db_session):
            record = await self._repository.rename(
                session_id, user_id, display_name.strip()
            )
        if record is None:
            raise _conflict("The session is no longer active.")
        await self._events.publish(
            SessionRenamed(user_id=user_id, session_id=session_id)
        )
        return record

    async def revoke(
        self,
        user_id: UUID,
        session_id: UUID,
        *,
        current_session_id: UUID,
    ) -> None:
        existing = await self._repository.get_for_user(session_id, user_id)
        if existing is None:
            raise _not_found()
        if session_id == current_session_id:
            raise _conflict("Use logout to end the current session.")
        if existing.is_revoked:
            raise _conflict("The session is already revoked.")
        async with _transaction(self._db_session):
            changed = await self._repository.revoke(session_id)
        if not changed:
            raise _conflict("The session is already revoked.")
        SESSION_REVOCATIONS.inc()
        await self._events.publish(
            SessionRevoked(user_id=user_id, session_id=session_id)
        )
        await self._snapshot_metrics(datetime.now(UTC))

    async def revoke_others(self, user_id: UUID, current_session_id: UUID) -> int:
        now = datetime.now(UTC)
        async with _transaction(self._db_session):
            count = await self._repository.revoke_others(
                user_id, current_session_id, now=now
            )
        SESSION_REVOCATIONS.inc(count)
        await self._events.publish(
            OtherSessionsRevoked(
                user_id=user_id,
                session_id=current_session_id,
                revoked_sessions=count,
            )
        )
        await self._snapshot_metrics(now)
        return count

    async def _snapshot_metrics(self, now: datetime) -> None:
        active, revoked = await self._repository.count_by_state(now=now)
        SESSION_ACTIVE.set(active)
        SESSION_REVOKED.set(revoked)


class SessionCleanupService:
    def __init__(
        self,
        db_session: AsyncSession,
        repository: RefreshSessionRepository,
        events: EventPublisher,
        *,
        retention: timedelta,
        batch_size: int,
    ) -> None:
        self._db_session = db_session
        self._repository = repository
        self._events = events
        self._retention = retention
        self._batch_size = batch_size

    async def run(self) -> tuple[int, int]:
        now = datetime.now(UTC)
        async with _transaction(self._db_session):
            newly_revoked = await self._repository.revoke_expired(
                now=now,
                limit=self._batch_size,
            )
            deleted = await self._repository.delete_expired_revoked(
                expired_before=now - self._retention,
                limit=self._batch_size,
            )
        SESSION_CLEANUP_EXECUTIONS.inc()
        if newly_revoked:
            await self._events.publish(SessionExpired(expired_sessions=newly_revoked))
        await self._events.publish(
            SessionCleanupCompleted(
                expired_sessions_revoked=newly_revoked,
                sessions_deleted=deleted,
            )
        )
        active, revoked = await self._repository.count_by_state(now=now)
        SESSION_ACTIVE.set(active)
        SESSION_REVOKED.set(revoked)
        return newly_revoked, deleted


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Session not found",
        detail="The requested session was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Session conflict",
        detail=detail,
        status_code=409,
    )


@asynccontextmanager
async def _transaction(session: AsyncSession) -> AsyncIterator[None]:
    transaction = (
        session.begin_nested() if session.in_transaction() else session.begin()
    )
    async with transaction:
        yield
