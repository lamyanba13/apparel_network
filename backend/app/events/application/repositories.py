from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.events.domain import ClaimedEvent, OutboxInspection


class ReliableOutboxRepository(Protocol):
    async def claim(
        self,
        event_names: Sequence[str],
        *,
        worker_id: str,
        now: datetime,
        lease_timeout: timedelta,
        limit: int,
    ) -> Sequence[ClaimedEvent]: ...

    async def mark_processed(
        self, event_id: UUID, *, worker_id: str, now: datetime
    ) -> bool: ...

    async def release(
        self, event_id: UUID, *, worker_id: str, now: datetime
    ) -> bool: ...

    async def mark_failed(
        self,
        event_id: UUID,
        *,
        worker_id: str,
        now: datetime,
        error: str,
        max_attempts: int,
        retry_base_seconds: int,
    ) -> bool: ...

    async def inspect_problematic(
        self, *, now: datetime, lease_timeout: timedelta, limit: int
    ) -> Sequence[OutboxInspection]: ...

    async def recover(
        self,
        event_id: UUID,
        *,
        now: datetime,
        lease_timeout: timedelta,
    ) -> OutboxInspection | None: ...
