from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.context import maybe_get_request_context
from app.common.errors import ErrorCode, FieldError
from app.common.events import DomainEvent, EventPublisher
from app.common.exceptions import AppError
from app.modules.identity.application.repositories import (
    EmailVerificationTokenRepository,
    LoginAttemptRepository,
    PasswordHistoryRepository,
    PasswordResetTokenRepository,
    RefreshSessionRepository,
    UserRepository,
)
from app.modules.identity.application.schemas import (
    EmailVerificationTokenCreate,
    PasswordHistoryCreate,
    PasswordResetTokenCreate,
    UserRecord,
)
from app.modules.identity.application.services import PasswordService
from app.modules.identity.domain.account_security import (
    PasswordPolicyValidator,
    PasswordViolation,
    PasswordViolationCode,
)
from app.modules.identity.domain.account_security_events import (
    AccountLocked,
    AccountSecurityCleanupCompleted,
    AccountUnlocked,
    EmailVerificationRequested,
    EmailVerified,
    PasswordChanged,
    PasswordPolicyViolation,
    PasswordResetCompleted,
    PasswordResetRequested,
    SuspiciousLoginDetected,
)
from app.observability.metrics import (
    ACCOUNT_SECURITY_CLEANUP_EXECUTIONS,
    ACCOUNT_SECURITY_CLEANUP_RECORDS,
)


class AccountNotificationKind(StrEnum):
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"


@dataclass(frozen=True, slots=True)
class AccountNotification:
    kind: AccountNotificationKind
    email: str
    token: SecretStr
    expires_at: datetime


class EmailNotifier(Protocol):
    async def send(self, notification: AccountNotification) -> None: ...


class SecurityNotifier(Protocol):
    async def notify(self, event: DomainEvent) -> None: ...


class NotificationPublisher(Protocol):
    async def publish(self, notification: AccountNotification) -> None: ...


class AccountTokenService(Protocol):
    def generate(self) -> SecretStr: ...

    def hash(self, token: SecretStr | str) -> str: ...


class AdministrativeAccountSecurityService(Protocol):
    """Future admin unlock boundary. Phase 2.5 exposes no admin API."""

    async def unlock_user(self, user_id: UUID, *, reason: str) -> None: ...


class AccountSecurityCleanupJob(Protocol):
    async def run(self) -> AccountSecurityCleanupResult: ...


@dataclass(frozen=True, slots=True)
class AccountSecurityCleanupResult:
    reset_tokens_deleted: int
    verification_tokens_deleted: int
    accounts_unlocked: int


@dataclass(frozen=True, slots=True)
class LockoutPolicy:
    delay_threshold: int
    short_threshold: int
    delay: timedelta
    short_lock: timedelta
    observation_window: timedelta
    maximum_lock: timedelta


class AccountLockoutService:
    """Progressive, expiring account lockout with no automatic permanent ban."""

    def __init__(
        self,
        users: UserRepository,
        attempts: LoginAttemptRepository,
        events: EventPublisher,
        policy: LockoutPolicy,
    ) -> None:
        self._users = users
        self._attempts = attempts
        self._events = events
        self._policy = policy

    async def before_attempt(
        self,
        user: UserRecord | None,
        *,
        now: datetime,
    ) -> None:
        if (
            user is not None
            and user.is_locked
            and user.locked_until is not None
            and user.locked_until <= now
            and await self._users.unlock(user.id)
        ):
            await self._events.publish(
                AccountUnlocked(
                    user_id=user.id,
                    correlation_id=_correlation_id(),
                )
            )

    async def after_failure(
        self,
        user: UserRecord | None,
        *,
        email: str,
        now: datetime,
    ) -> None:
        if user is None:
            return
        failures = await self._attempts.count_recent_failures(
            email,
            since=now - self._policy.observation_window,
        )
        duration = self._duration(failures)
        if duration is None:
            return
        reason = (
            "progressive_short_lock"
            if failures >= self._policy.short_threshold
            else "progressive_delay"
        )
        locked_until = now + duration
        await self._users.set_lock(
            user.id,
            locked_until=locked_until,
            reason=reason,
        )
        await self._events.publish(
            AccountLocked(
                user_id=user.id,
                locked_until=locked_until,
                reason=reason,
                correlation_id=_correlation_id(),
            )
        )
        if failures >= self._policy.short_threshold:
            await self._events.publish(
                SuspiciousLoginDetected(
                    user_id=user.id,
                    reason="repeated_authentication_failures",
                    correlation_id=_correlation_id(),
                )
            )

    async def after_success(
        self,
        user: UserRecord,
        *,
        now: datetime,
    ) -> None:
        await self.before_attempt(user, now=now)

    def _duration(self, failures: int) -> timedelta | None:
        if failures < self._policy.delay_threshold:
            return None
        if failures < self._policy.short_threshold:
            return self._policy.delay
        escalation_step = (
            failures - self._policy.short_threshold
        ) // self._policy.short_threshold
        seconds = self._policy.short_lock.total_seconds() * (2**escalation_step)
        return timedelta(
            seconds=min(seconds, self._policy.maximum_lock.total_seconds())
        )


class AccountSecurityService:
    """Credential recovery and verification use cases."""

    def __init__(
        self,
        db_session: AsyncSession,
        users: UserRepository,
        histories: PasswordHistoryRepository,
        reset_tokens: PasswordResetTokenRepository,
        verification_tokens: EmailVerificationTokenRepository,
        sessions: RefreshSessionRepository,
        passwords: PasswordService,
        token_service: AccountTokenService,
        policy: PasswordPolicyValidator,
        events: EventPublisher,
        notifications: NotificationPublisher | None,
        *,
        history_depth: int,
        reset_lifetime: timedelta,
        verification_lifetime: timedelta,
    ) -> None:
        self._db_session = db_session
        self._users = users
        self._histories = histories
        self._reset_tokens = reset_tokens
        self._verification_tokens = verification_tokens
        self._sessions = sessions
        self._passwords = passwords
        self._token_service = token_service
        self._policy = policy
        self._events = events
        self._notifications = notifications
        self._history_depth = history_depth
        self._reset_lifetime = reset_lifetime
        self._verification_lifetime = verification_lifetime

    async def change_password(
        self,
        *,
        user_id: UUID,
        current_session_id: UUID,
        current_password: SecretStr,
        new_password: SecretStr,
    ) -> None:
        user = await self._users.get_by_id(
            user_id,
            include_deleted=True,
            for_update=True,
        )
        if user is None or not self._passwords.verify_password(
            current_password,
            user.password_hash.get_secret_value(),
        ):
            raise AppError(
                code=ErrorCode.UNAUTHORIZED,
                title="Password change failed",
                detail="The current password is incorrect.",
                status_code=401,
            )
        await self._validate_candidate(user, new_password)
        new_hash = self._passwords.hash_password(new_password)
        async with _transaction(self._db_session):
            await self._histories.add(
                PasswordHistoryCreate(
                    user_id=user.id,
                    password_hash=user.password_hash,
                )
            )
            await self._users.update_password(user.id, new_hash)
            revoked = await self._sessions.revoke_others(
                user.id,
                current_session_id,
                now=datetime.now(UTC),
            )
        await self._events.publish(
            PasswordChanged(
                user_id=user.id,
                revoked_sessions=revoked,
                correlation_id=_correlation_id(),
            )
        )

    async def request_password_reset(self, email: str) -> None:
        now = datetime.now(UTC)
        token = self._token_service.generate()
        user = await self._users.get_by_email(email, include_deleted=True)
        notification: AccountNotification | None = None
        if user is not None and user.is_active and user.deleted_at is None:
            expires_at = now + self._reset_lifetime
            async with _transaction(self._db_session):
                await self._reset_tokens.invalidate_for_user(user.id)
                await self._reset_tokens.add(
                    PasswordResetTokenCreate(
                        user_id=user.id,
                        token_hash=self._token_service.hash(token),
                        expires_at=expires_at,
                    )
                )
            notification = AccountNotification(
                kind=AccountNotificationKind.PASSWORD_RESET,
                email=user.email,
                token=token,
                expires_at=expires_at,
            )
        await self._events.publish(
            PasswordResetRequested(
                accepted=True,
                correlation_id=_correlation_id(),
            )
        )
        if notification is not None and self._notifications is not None:
            await self._notifications.publish(notification)

    async def reset_password(
        self,
        *,
        token: SecretStr,
        new_password: SecretStr,
    ) -> None:
        now = datetime.now(UTC)
        token_hash = self._token_service.hash(token)
        record = await self._reset_tokens.get_by_hash(token_hash)
        if record is None or record.is_used or record.expires_at <= now:
            raise _invalid_account_token()
        user = await self._users.get_by_id(
            record.user_id,
            include_deleted=True,
            for_update=True,
        )
        if user is None or user.deleted_at is not None:
            raise _invalid_account_token()
        await self._validate_candidate(user, new_password)
        new_hash = self._passwords.hash_password(new_password)
        async with _transaction(self._db_session):
            if not await self._reset_tokens.consume(token_hash, now=now):
                raise _invalid_account_token()
            await self._histories.add(
                PasswordHistoryCreate(
                    user_id=user.id,
                    password_hash=user.password_hash,
                )
            )
            await self._users.update_password(user.id, new_hash)
            await self._reset_tokens.invalidate_for_user(user.id)
            revoked = await self._sessions.revoke_all_for_user(user.id)
        await self._events.publish(
            PasswordResetCompleted(
                user_id=user.id,
                revoked_sessions=revoked,
                correlation_id=_correlation_id(),
            )
        )

    async def request_email_verification(self, email: str) -> None:
        now = datetime.now(UTC)
        token = self._token_service.generate()
        user = await self._users.get_by_email(email, include_deleted=True)
        notification: AccountNotification | None = None
        if (
            user is not None
            and user.is_active
            and user.deleted_at is None
            and not user.is_email_verified
        ):
            expires_at = now + self._verification_lifetime
            async with _transaction(self._db_session):
                await self._verification_tokens.invalidate_for_user(user.id)
                await self._verification_tokens.add(
                    EmailVerificationTokenCreate(
                        user_id=user.id,
                        token_hash=self._token_service.hash(token),
                        expires_at=expires_at,
                    )
                )
            notification = AccountNotification(
                kind=AccountNotificationKind.EMAIL_VERIFICATION,
                email=user.email,
                token=token,
                expires_at=expires_at,
            )
        await self._events.publish(
            EmailVerificationRequested(
                accepted=True,
                correlation_id=_correlation_id(),
            )
        )
        if notification is not None and self._notifications is not None:
            await self._notifications.publish(notification)

    async def verify_email(self, token: SecretStr) -> None:
        now = datetime.now(UTC)
        token_hash = self._token_service.hash(token)
        record = await self._verification_tokens.get_by_hash(token_hash)
        if record is None or record.is_used or record.expires_at <= now:
            return
        changed = False
        async with _transaction(self._db_session):
            if await self._verification_tokens.consume(token_hash, now=now):
                changed = await self._users.mark_email_verified(
                    record.user_id,
                    at=now,
                )
                await self._verification_tokens.invalidate_for_user(record.user_id)
        if changed:
            await self._events.publish(
                EmailVerified(
                    user_id=record.user_id,
                    correlation_id=_correlation_id(),
                )
            )

    async def _validate_candidate(
        self,
        user: UserRecord,
        candidate: SecretStr,
    ) -> None:
        violations = list(self._policy.validate_password(candidate, email=user.email))
        hashes: list[str] = [user.password_hash.get_secret_value()]
        hashes.extend(
            record.password_hash.get_secret_value()
            for record in await self._histories.list_recent(
                user.id,
                limit=self._history_depth,
            )
        )
        if any(
            self._passwords.verify_password(candidate, password_hash)
            for password_hash in hashes
        ):
            violations.append(
                PasswordViolation(
                    PasswordViolationCode.RECENTLY_USED,
                    "Choose a password you have not used recently.",
                )
            )
        if not violations:
            return
        await self._events.publish(
            PasswordPolicyViolation(
                violation_codes=tuple(violation.code.value for violation in violations),
                correlation_id=_correlation_id(),
            )
        )
        raise AppError(
            code=ErrorCode.VALIDATION_ERROR,
            title="Password policy violation",
            detail="The new password does not meet the security policy.",
            status_code=422,
            errors=[
                FieldError(
                    field="new_password",
                    code=violation.code.value,
                    message=violation.message,
                )
                for violation in violations
            ],
        )


class AccountSecurityCleanupService(AccountSecurityCleanupJob):
    def __init__(
        self,
        db_session: AsyncSession,
        users: UserRepository,
        reset_tokens: PasswordResetTokenRepository,
        verification_tokens: EmailVerificationTokenRepository,
        events: EventPublisher,
        *,
        batch_size: int,
    ) -> None:
        self._db_session = db_session
        self._users = users
        self._reset_tokens = reset_tokens
        self._verification_tokens = verification_tokens
        self._events = events
        self._batch_size = batch_size

    async def run(self) -> AccountSecurityCleanupResult:
        now = datetime.now(UTC)
        async with _transaction(self._db_session):
            reset_count = await self._reset_tokens.delete_expired(
                now=now,
                limit=self._batch_size,
            )
            verification_count = await self._verification_tokens.delete_expired(
                now=now,
                limit=self._batch_size,
            )
            unlocked_ids: Sequence[UUID] = await self._users.unlock_expired(
                now=now,
                limit=self._batch_size,
            )
        result = AccountSecurityCleanupResult(
            reset_tokens_deleted=reset_count,
            verification_tokens_deleted=verification_count,
            accounts_unlocked=len(unlocked_ids),
        )
        ACCOUNT_SECURITY_CLEANUP_EXECUTIONS.inc()
        ACCOUNT_SECURITY_CLEANUP_RECORDS.inc(
            reset_count + verification_count + len(unlocked_ids)
        )
        for user_id in unlocked_ids:
            await self._events.publish(
                AccountUnlocked(
                    user_id=user_id,
                    correlation_id=_correlation_id(),
                )
            )
        await self._events.publish(
            AccountSecurityCleanupCompleted(
                reset_tokens_deleted=reset_count,
                verification_tokens_deleted=verification_count,
                accounts_unlocked=len(unlocked_ids),
                correlation_id=_correlation_id(),
            )
        )
        return result


def _invalid_account_token() -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Invalid or expired token",
        detail="The account security token is invalid or has expired.",
        status_code=400,
    )


@asynccontextmanager
async def _transaction(session: AsyncSession) -> AsyncIterator[None]:
    transaction = (
        session.begin_nested() if session.in_transaction() else session.begin()
    )
    async with transaction:
        yield


def _correlation_id() -> UUID | None:
    context = maybe_get_request_context()
    return context.correlation_id if context is not None else None
