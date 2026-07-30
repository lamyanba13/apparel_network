from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.common.idempotency.keys import IdempotencyKey
from app.common.types import JsonObject


class IdempotencyClaimStatus(StrEnum):
    """Outcome of atomically claiming a scoped key."""

    ACQUIRED = "acquired"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"


@dataclass(frozen=True, slots=True)
class StoredIdempotencyResult:
    """Safe replay data retained by a future PostgreSQL implementation."""

    status_code: int
    body: JsonObject


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    """Provider-neutral claim result."""

    status: IdempotencyClaimStatus
    result: StoredIdempotencyResult | None = None


class IdempotencyStore(Protocol):
    """Port for future authoritative PostgreSQL idempotency records."""

    async def claim(
        self,
        *,
        scope: str,
        key: IdempotencyKey,
        fingerprint: str,
    ) -> IdempotencyClaim: ...

    async def complete(
        self,
        *,
        scope: str,
        key: IdempotencyKey,
        fingerprint: str,
        result: StoredIdempotencyResult,
    ) -> None: ...

    async def release(
        self,
        *,
        scope: str,
        key: IdempotencyKey,
        fingerprint: str,
    ) -> None: ...
