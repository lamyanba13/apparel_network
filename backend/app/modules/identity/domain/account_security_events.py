from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import JsonValue

from app.modules.identity.domain.events import AuthenticationEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class UserSecurityEvent(AuthenticationEvent):
    user_id: UUID

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"user_id": str(self.user_id)}


@dataclass(frozen=True, slots=True, kw_only=True)
class PasswordChanged(UserSecurityEvent):
    revoked_sessions: int
    event_name: ClassVar[str] = "identity.password_changed"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "user_id": str(self.user_id),
            "revoked_sessions": self.revoked_sessions,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PasswordResetRequested(AuthenticationEvent):
    accepted: bool
    event_name: ClassVar[str] = "identity.password_reset_requested"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"accepted": self.accepted}


@dataclass(frozen=True, slots=True, kw_only=True)
class PasswordResetCompleted(UserSecurityEvent):
    revoked_sessions: int
    event_name: ClassVar[str] = "identity.password_reset_completed"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "user_id": str(self.user_id),
            "revoked_sessions": self.revoked_sessions,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class EmailVerificationRequested(AuthenticationEvent):
    accepted: bool
    event_name: ClassVar[str] = "identity.email_verification_requested"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"accepted": self.accepted}


@dataclass(frozen=True, slots=True, kw_only=True)
class EmailVerified(UserSecurityEvent):
    event_name: ClassVar[str] = "identity.email_verified"


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountLocked(UserSecurityEvent):
    locked_until: datetime
    reason: str
    event_name: ClassVar[str] = "identity.account_locked"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "user_id": str(self.user_id),
            "locked_until": self.locked_until.isoformat(),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountUnlocked(UserSecurityEvent):
    event_name: ClassVar[str] = "identity.account_unlocked"


@dataclass(frozen=True, slots=True, kw_only=True)
class PasswordPolicyViolation(AuthenticationEvent):
    violation_codes: tuple[str, ...]
    event_name: ClassVar[str] = "identity.password_policy_violation"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"violation_codes": list(self.violation_codes)}


@dataclass(frozen=True, slots=True, kw_only=True)
class SuspiciousLoginDetected(UserSecurityEvent):
    reason: str
    event_name: ClassVar[str] = "identity.suspicious_login_detected"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {"user_id": str(self.user_id), "reason": self.reason}


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountSecurityCleanupCompleted(AuthenticationEvent):
    reset_tokens_deleted: int
    verification_tokens_deleted: int
    accounts_unlocked: int
    event_name: ClassVar[str] = "identity.account_security_cleanup_completed"

    @property
    def payload(self) -> dict[str, JsonValue]:
        return {
            "reset_tokens_deleted": self.reset_tokens_deleted,
            "verification_tokens_deleted": self.verification_tokens_deleted,
            "accounts_unlocked": self.accounts_unlocked,
        }
