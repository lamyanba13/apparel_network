from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class StoreMembershipRole(StrEnum):
    """Store-local responsibilities; never used as an authorization shortcut."""

    OWNER = "owner"
    MANAGER = "manager"
    STAFF = "staff"


class StoreMembershipStatus(StrEnum):
    """Lifecycle state of a Store membership or invitation."""

    PENDING = "pending"
    ACTIVE = "active"
    DECLINED = "declined"
    SUSPENDED = "suspended"
    REMOVED = "removed"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class StoreMembership:
    id: UUID
    store_id: UUID
    user_id: UUID
    role: StoreMembershipRole
    status: StoreMembershipStatus
    invited_by_id: UUID
    invitation_expires_at: datetime | None
    accepted_at: datetime | None
    removed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
