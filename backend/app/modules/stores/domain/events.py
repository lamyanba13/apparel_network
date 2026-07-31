from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7

from app.modules.stores.domain.models import StoreStatus, VerificationStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreEvent:
    store_id: UUID
    owner_id: UUID
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None

    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "store_id": str(self.store_id),
            "owner_id": str(self.owner_id),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreCreated(StoreEvent):
    event_name: ClassVar[str] = "store.created"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreUpdated(StoreEvent):
    event_name: ClassVar[str] = "store.updated"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreVerificationEvent(StoreEvent):
    status: StoreStatus
    verification_status: VerificationStatus

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "store_id": str(self.store_id),
            "owner_id": str(self.owner_id),
            "store_status": self.status.value,
            "verification_status": self.verification_status.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreSubmitted(StoreVerificationEvent):
    event_name: ClassVar[str] = "store.submitted"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreVerified(StoreVerificationEvent):
    verification_id: UUID | None = None
    actor_user_id: UUID | None = None

    event_name: ClassVar[str] = "store.verified"

    @property
    def payload(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "store_id": str(self.store_id),
            "owner_id": str(self.owner_id),
            "store_status": self.status.value,
            "verification_status": self.verification_status.value,
        }
        if self.verification_id is not None:
            payload["verification_id"] = str(self.verification_id)
        if self.actor_user_id is not None:
            payload["actor_user_id"] = str(self.actor_user_id)
        return payload


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreOperationalEvent(StoreEvent):
    status: StoreStatus

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "store_id": str(self.store_id),
            "owner_id": str(self.owner_id),
            "store_status": self.status.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreSuspended(StoreOperationalEvent):
    event_name: ClassVar[str] = "store.suspended"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreClosed(StoreOperationalEvent):
    event_name: ClassVar[str] = "store.closed"
