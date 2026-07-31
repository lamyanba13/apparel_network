from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7

from app.modules.stores.domain.verification import StoreVerificationStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreVerificationEvent:
    verification_id: UUID
    store_id: UUID
    actor_user_id: UUID
    status: StoreVerificationStatus
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None

    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "verification_id": str(self.verification_id),
            "store_id": str(self.store_id),
            "actor_user_id": str(self.actor_user_id),
            "verification_status": self.status.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreVerificationSubmitted(StoreVerificationEvent):
    event_name: ClassVar[str] = "store.verification.submitted"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreVerificationStarted(StoreVerificationEvent):
    event_name: ClassVar[str] = "store.verification.started"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreVerificationRejected(StoreVerificationEvent):
    event_name: ClassVar[str] = "store.verification.rejected"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreVerificationReopened(StoreVerificationEvent):
    event_name: ClassVar[str] = "store.verification.reopened"
