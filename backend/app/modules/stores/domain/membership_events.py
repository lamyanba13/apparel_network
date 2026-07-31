from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7

from app.modules.stores.domain.membership import (
    StoreMembershipRole,
    StoreMembershipStatus,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMembershipEvent:
    membership_id: UUID
    store_id: UUID
    user_id: UUID
    actor_user_id: UUID
    role: StoreMembershipRole
    status: StoreMembershipStatus
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None

    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "membership_id": str(self.membership_id),
            "store_id": str(self.store_id),
            "user_id": str(self.user_id),
            "actor_user_id": str(self.actor_user_id),
            "membership_role": self.role.value,
            "membership_status": self.status.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMemberInvited(StoreMembershipEvent):
    event_name: ClassVar[str] = "store.member.invited"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMemberAccepted(StoreMembershipEvent):
    event_name: ClassVar[str] = "store.member.accepted"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMemberDeclined(StoreMembershipEvent):
    event_name: ClassVar[str] = "store.member.declined"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMemberSuspended(StoreMembershipEvent):
    event_name: ClassVar[str] = "store.member.suspended"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMemberReactivated(StoreMembershipEvent):
    event_name: ClassVar[str] = "store.member.reactivated"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMemberRoleChanged(StoreMembershipEvent):
    event_name: ClassVar[str] = "store.member.role_changed"


@dataclass(frozen=True, slots=True, kw_only=True)
class StoreMemberRemoved(StoreMembershipEvent):
    event_name: ClassVar[str] = "store.member.removed"
