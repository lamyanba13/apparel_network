from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.events.application.repositories import ReliableOutboxRepository
from app.events.domain import OutboxInspection


class OutboxOperationsService:
    def __init__(
        self,
        repository: ReliableOutboxRepository,
        *,
        lease_seconds: int,
    ) -> None:
        self._repository = repository
        self._lease_timeout = timedelta(seconds=lease_seconds)

    async def inspect(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> Sequence[OutboxInspection]:
        return await self._repository.inspect_problematic(
            now=now or datetime.now(UTC),
            lease_timeout=self._lease_timeout,
            limit=limit,
        )

    async def recover(
        self, event_id: UUID, *, now: datetime | None = None
    ) -> OutboxInspection | None:
        return await self._repository.recover(
            event_id,
            now=now or datetime.now(UTC),
            lease_timeout=self._lease_timeout,
        )
