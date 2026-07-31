from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue

from app.modules.identity.domain.events import AuthenticationEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizationDecisionEvent(AuthenticationEvent):
    user_id: UUID
    requirement: str

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"user_id": str(self.user_id), "requirement": self.requirement}


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizationGranted(AuthorizationDecisionEvent):
    event_name: ClassVar[str] = "identity.authorization_granted"


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizationDenied(AuthorizationDecisionEvent):
    event_name: ClassVar[str] = "identity.authorization_denied"


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionCacheHit(AuthenticationEvent):
    event_name: ClassVar[str] = "identity.permission_cache_hit"


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionCacheMiss(AuthenticationEvent):
    event_name: ClassVar[str] = "identity.permission_cache_miss"


@dataclass(frozen=True, slots=True, kw_only=True)
class RoleAssignmentEvent(AuthenticationEvent):
    user_id: UUID
    role_name: str
    actor_user_id: UUID | None = None

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "user_id": str(self.user_id),
            "role_name": self.role_name,
            "actor_user_id": (
                str(self.actor_user_id) if self.actor_user_id is not None else None
            ),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RoleAssigned(RoleAssignmentEvent):
    event_name: ClassVar[str] = "identity.role_assigned"


@dataclass(frozen=True, slots=True, kw_only=True)
class RoleRevoked(RoleAssignmentEvent):
    event_name: ClassVar[str] = "identity.role_revoked"


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionGrantEvent(AuthenticationEvent):
    role_name: str
    permission_name: str
    actor_user_id: UUID | None = None

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "role_name": self.role_name,
            "permission_name": self.permission_name,
            "actor_user_id": (
                str(self.actor_user_id) if self.actor_user_id is not None else None
            ),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionGranted(PermissionGrantEvent):
    event_name: ClassVar[str] = "identity.permission_granted"


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionRevoked(PermissionGrantEvent):
    event_name: ClassVar[str] = "identity.permission_revoked"
