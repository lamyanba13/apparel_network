from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue

from app.modules.identity.domain.events import AuthenticationEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionSecurityEvent(AuthenticationEvent):
    user_id: UUID
    session_id: UUID

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"user_id": str(self.user_id), "session_id": str(self.session_id)}


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionCreated(SessionSecurityEvent):
    event_name: ClassVar[str] = "identity.session_created"


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionRenamed(SessionSecurityEvent):
    event_name: ClassVar[str] = "identity.session_renamed"


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionRevoked(SessionRenamed):
    event_name: ClassVar[str] = "identity.session_revoked"


@dataclass(frozen=True, slots=True, kw_only=True)
class OtherSessionsRevoked(SessionRenamed):
    revoked_sessions: int
    event_name: ClassVar[str] = "identity.other_sessions_revoked"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "user_id": str(self.user_id),
            "session_id": str(self.session_id),
            "revoked_sessions": self.revoked_sessions,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionCleanupCompleted(AuthenticationEvent):
    expired_sessions_revoked: int
    sessions_deleted: int
    event_name: ClassVar[str] = "identity.session_cleanup_completed"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "expired_sessions_revoked": self.expired_sessions_revoked,
            "sessions_deleted": self.sessions_deleted,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionExpired(AuthenticationEvent):
    expired_sessions: int
    event_name: ClassVar[str] = "identity.session_expired"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"expired_sessions": self.expired_sessions}


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionRiskUpdated(SessionSecurityEvent):
    risk_score: int | None
    event_name: ClassVar[str] = "identity.session_risk_updated"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "user_id": str(self.user_id),
            "session_id": str(self.session_id),
            "risk_score": self.risk_score,
        }
