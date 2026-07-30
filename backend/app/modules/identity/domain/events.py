from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue
from uuid6 import uuid7


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthenticationEvent:
    event_id: UUID = field(default_factory=uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None

    event_name: ClassVar[str]
    schema_version: ClassVar[int] = 1

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthenticationSucceeded(AuthenticationEvent):
    user_id: UUID
    session_id: UUID
    event_name: ClassVar[str] = "identity.authentication_succeeded"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"user_id": str(self.user_id), "session_id": str(self.session_id)}


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthenticationFailed(AuthenticationEvent):
    reason: str = "invalid_credentials"
    event_name: ClassVar[str] = "identity.authentication_failed"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"reason": self.reason}


@dataclass(frozen=True, slots=True, kw_only=True)
class RefreshRotated(AuthenticationEvent):
    user_id: UUID
    session_id: UUID
    family_id: UUID
    rotation_count: int
    event_name: ClassVar[str] = "identity.refresh_rotated"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "user_id": str(self.user_id),
            "session_id": str(self.session_id),
            "family_id": str(self.family_id),
            "rotation_count": self.rotation_count,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RefreshReuseDetected(AuthenticationEvent):
    user_id: UUID
    session_id: UUID
    family_id: UUID
    event_name: ClassVar[str] = "identity.refresh_reuse_detected"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "user_id": str(self.user_id),
            "session_id": str(self.session_id),
            "family_id": str(self.family_id),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class LogoutCompleted(AuthenticationEvent):
    user_id: UUID | None = None
    session_id: UUID | None = None
    revoked_sessions: int = 1
    event_name: ClassVar[str] = "identity.logout_completed"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "user_id": str(self.user_id) if self.user_id is not None else None,
            "session_id": (
                str(self.session_id) if self.session_id is not None else None
            ),
            "revoked_sessions": self.revoked_sessions,
        }
