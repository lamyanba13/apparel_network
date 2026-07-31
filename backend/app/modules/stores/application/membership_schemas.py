from dataclasses import dataclass
from uuid import UUID

from app.modules.stores.domain import StoreMembershipRole, StoreMembershipStatus


@dataclass(frozen=True, slots=True)
class StoreMembershipInvitation:
    user_id: UUID
    role: StoreMembershipRole


@dataclass(frozen=True, slots=True)
class StoreMembershipUpdate:
    expected_version: int
    role: StoreMembershipRole | None = None
    status: StoreMembershipStatus | None = None
