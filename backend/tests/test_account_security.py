from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.common.config import Settings, get_settings
from app.common.events import DomainEvent
from app.common.exceptions import AppError
from app.common.middleware.rate_limit import authentication_rate_limit_scope
from app.common.rate_limiting import RateLimitScope
from app.main import create_application
from app.modules.identity.application.account_security import (
    AccountLockoutService,
    AccountNotification,
    AccountSecurityCleanupService,
    AccountSecurityService,
    LockoutPolicy,
)
from app.modules.identity.application.schemas import (
    LoginAttemptCreate,
    RefreshSessionCreate,
    UserCreate,
)
from app.modules.identity.domain.account_security import (
    PasswordPolicy,
    PasswordPolicyValidator,
    PasswordViolationCode,
)
from app.modules.identity.domain.account_security_events import (
    AccountLocked,
    AccountSecurityCleanupCompleted,
    EmailVerified,
    PasswordChanged,
    PasswordResetCompleted,
)
from app.modules.identity.infrastructure.persistence.models import (
    EmailVerificationTokenModel,
    PasswordHistoryModel,
    PasswordResetTokenModel,
    RefreshSessionModel,
    UserModel,
)
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyEmailVerificationTokenRepository,
    SqlAlchemyLoginAttemptRepository,
    SqlAlchemyPasswordHistoryRepository,
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemyRefreshSessionRepository,
    SqlAlchemyUserRepository,
)
from app.modules.identity.infrastructure.security import (
    OpaqueAccountTokenService,
    PwdlibPasswordService,
)
from app.observability.metrics import (
    ACCOUNT_LOCKOUTS,
    ACCOUNT_SECURITY_CLEANUP_EXECUTIONS,
    EMAIL_VERIFICATIONS,
    PASSWORD_CHANGES,
    PASSWORD_RESETS,
    SECURITY_EVENTS,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CURRENT_PASSWORD = SecretStr("Current-Secret-42!")
NEW_PASSWORD = SecretStr("Different-Strong-84!")


@dataclass
class RecordingPublisher:
    events: list[DomainEvent] = field(default_factory=list)

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


@dataclass
class RecordingNotifications:
    notifications: list[AccountNotification] = field(default_factory=list)

    async def publish(self, notification: AccountNotification) -> None:
        self.notifications.append(notification)


@pytest.fixture
def migrated_database(
    monkeypatch: MonkeyPatch,
    database_url: str,
) -> Iterator[None]:
    monkeypatch.chdir(BACKEND_ROOT)
    monkeypatch.setenv("FASHION_NETWORK_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        command.upgrade(Config(BACKEND_ROOT / "alembic.ini"), "head")
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def account_session(
    migrated_database: None,
    database_url: str,
) -> AsyncIterator[AsyncSession]:
    del migrated_database
    engine = create_async_engine(database_url, pool_pre_ping=True)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()
    await engine.dispose()


def password_policy(settings: Settings) -> PasswordPolicyValidator:
    return PasswordPolicyValidator(
        PasswordPolicy(
            minimum_length=settings.password_min_length,
            maximum_length=settings.password_max_length,
            require_uppercase=settings.password_require_uppercase,
            require_lowercase=settings.password_require_lowercase,
            require_number=settings.password_require_number,
            require_symbol=settings.password_require_symbol,
            forbidden_passwords=frozenset(
                value.casefold() for value in settings.password_forbidden_values
            ),
        )
    )


def make_service(
    session: AsyncSession,
    settings: Settings,
    events: RecordingPublisher,
    notifications: RecordingNotifications | None = None,
) -> AccountSecurityService:
    return AccountSecurityService(
        session,
        SqlAlchemyUserRepository(session),
        SqlAlchemyPasswordHistoryRepository(session),
        SqlAlchemyPasswordResetTokenRepository(session),
        SqlAlchemyEmailVerificationTokenRepository(session),
        SqlAlchemyRefreshSessionRepository(session),
        PwdlibPasswordService(),
        OpaqueAccountTokenService(),
        password_policy(settings),
        events,
        notifications,
        history_depth=settings.password_history_depth,
        reset_lifetime=timedelta(
            minutes=settings.password_reset_token_lifetime_minutes
        ),
        verification_lifetime=timedelta(
            hours=settings.email_verification_token_lifetime_hours
        ),
    )


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    verified: bool = True,
) -> UUID:
    record = await SqlAlchemyUserRepository(session).add(
        UserCreate(
            email=email,
            display_name="Account Security Test",
            password_hash=PwdlibPasswordService().hash_password(CURRENT_PASSWORD),
            is_email_verified=verified,
            email_verified_at=datetime.now(UTC) if verified else None,
        )
    )
    return record.id


async def create_session(
    session: AsyncSession,
    user_id: UUID,
    *,
    token_hash: str,
) -> UUID:
    now = datetime.now(UTC)
    record = await SqlAlchemyRefreshSessionRepository(session).add(
        RefreshSessionCreate(
            user_id=user_id,
            refresh_token_hash=token_hash,
            family_id=UUID(int=int(token_hash[0], 16) + 1),
            device_name="Test device",
            display_name="Test device",
            browser="Test",
            operating_system="Test",
            ip_address="127.0.0.1",
            user_agent="Account security test",
            last_activity_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=30),
        )
    )
    return record.id


def test_password_policy_returns_structured_violations(
    test_settings: Settings,
) -> None:
    violations = password_policy(test_settings).validate_password(
        SecretStr("account"),
        email="account@example.com",
    )

    assert {
        PasswordViolationCode.TOO_SHORT,
        PasswordViolationCode.UPPERCASE_REQUIRED,
        PasswordViolationCode.NUMBER_REQUIRED,
        PasswordViolationCode.SYMBOL_REQUIRED,
        PasswordViolationCode.EMAIL_SIMILARITY,
    } <= {violation.code for violation in violations}


def test_account_tokens_have_256_bit_entropy_and_are_hashed_only() -> None:
    service = OpaqueAccountTokenService()
    token = service.generate()
    plaintext = token.get_secret_value()
    digest = service.hash(token)

    assert len(plaintext) >= 43
    assert len(digest) == 64
    assert digest != plaintext
    assert plaintext not in repr(token)


async def test_password_change_keeps_current_and_revokes_other_sessions(
    account_session: AsyncSession,
    test_settings: Settings,
) -> None:
    events = RecordingPublisher()
    user_id = await create_user(
        account_session,
        email="change@example.com",
    )
    current_id = await create_session(account_session, user_id, token_hash="a" * 64)
    other_id = await create_session(account_session, user_id, token_hash="b" * 64)

    await make_service(account_session, test_settings, events).change_password(
        user_id=user_id,
        current_session_id=current_id,
        current_password=CURRENT_PASSWORD,
        new_password=NEW_PASSWORD,
    )

    current = await account_session.get(RefreshSessionModel, current_id)
    other = await account_session.get(RefreshSessionModel, other_id)
    user = await account_session.get(UserModel, user_id)
    assert current is not None and not current.is_revoked
    assert other is not None and other.is_revoked
    assert user is not None
    assert PwdlibPasswordService().verify_password(NEW_PASSWORD, user.password_hash)
    assert (
        await account_session.scalar(
            select(PasswordHistoryModel).where(PasswordHistoryModel.user_id == user_id)
        )
        is not None
    )
    assert any(isinstance(event, PasswordChanged) for event in events.events)


async def test_password_reset_is_single_use_and_never_persists_plaintext(
    account_session: AsyncSession,
    test_settings: Settings,
) -> None:
    events = RecordingPublisher()
    notifications = RecordingNotifications()
    user_id = await create_user(account_session, email="reset@example.com")
    await create_session(account_session, user_id, token_hash="c" * 64)
    service = make_service(account_session, test_settings, events, notifications)

    await service.request_password_reset("reset@example.com")
    token = notifications.notifications[0].token
    persisted = await account_session.scalar(
        select(PasswordResetTokenModel).where(
            PasswordResetTokenModel.user_id == user_id
        )
    )
    assert persisted is not None
    assert persisted.token_hash != token.get_secret_value()

    await service.reset_password(token=token, new_password=NEW_PASSWORD)
    with pytest.raises(AppError):
        await service.reset_password(token=token, new_password=NEW_PASSWORD)

    refresh_session = await account_session.scalar(
        select(RefreshSessionModel).where(RefreshSessionModel.user_id == user_id)
    )
    assert refresh_session is not None and refresh_session.is_revoked
    assert any(isinstance(event, PasswordResetCompleted) for event in events.events)


async def test_recovery_requests_do_not_enumerate_accounts(
    account_session: AsyncSession,
    test_settings: Settings,
) -> None:
    events = RecordingPublisher()
    notifications = RecordingNotifications()
    service = make_service(account_session, test_settings, events, notifications)

    await service.request_password_reset("missing@example.com")
    await service.request_email_verification("missing@example.com")

    assert notifications.notifications == []


async def test_email_verification_is_idempotent(
    account_session: AsyncSession,
    test_settings: Settings,
) -> None:
    events = RecordingPublisher()
    notifications = RecordingNotifications()
    user_id = await create_user(
        account_session,
        email="verify@example.com",
        verified=False,
    )
    service = make_service(account_session, test_settings, events, notifications)
    await service.request_email_verification("verify@example.com")
    token = notifications.notifications[0].token

    await service.verify_email(token)
    await service.verify_email(token)

    user = await account_session.get(UserModel, user_id)
    persisted_token = await account_session.scalar(
        select(EmailVerificationTokenModel).where(
            EmailVerificationTokenModel.user_id == user_id
        )
    )
    assert user is not None and user.is_email_verified
    assert user.email_verified_at is not None
    assert persisted_token is not None and persisted_token.is_used
    assert sum(isinstance(event, EmailVerified) for event in events.events) == 1


async def test_progressive_lockout_and_expiry_unlock(
    account_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    user_id = await create_user(account_session, email="locked@example.com")
    users = SqlAlchemyUserRepository(account_session)
    attempts = SqlAlchemyLoginAttemptRepository(account_session)
    service = AccountLockoutService(
        users,
        attempts,
        events,
        LockoutPolicy(
            delay_threshold=5,
            short_threshold=10,
            delay=timedelta(seconds=30),
            short_lock=timedelta(minutes=15),
            observation_window=timedelta(minutes=15),
            maximum_lock=timedelta(hours=4),
        ),
    )
    now = datetime.now(UTC)
    for offset in range(5):
        await attempts.add(
            LoginAttemptCreate(
                occurred_at=now + timedelta(milliseconds=offset),
                ip_address="127.0.0.1",
                email="locked@example.com",
                success=False,
                reason="invalid_credentials",
            )
        )
    user = await users.get_by_id(user_id, include_deleted=True)
    await service.after_failure(
        user,
        email="locked@example.com",
        now=now + timedelta(seconds=1),
    )
    locked = await users.get_by_id(user_id, include_deleted=True)
    assert locked is not None and locked.is_locked
    assert locked.locked_until is not None
    assert locked.lock_reason == "progressive_delay"
    assert any(isinstance(event, AccountLocked) for event in events.events)

    await service.before_attempt(
        locked,
        now=locked.locked_until + timedelta(seconds=1),
    )
    unlocked = await users.get_by_id(user_id, include_deleted=True)
    assert unlocked is not None and not unlocked.is_locked
    assert unlocked.unlock_count == 1


async def test_successful_login_resets_the_failure_window(
    account_session: AsyncSession,
) -> None:
    attempts = SqlAlchemyLoginAttemptRepository(account_session)
    now = datetime.now(UTC)
    for occurred_at, success in (
        (now - timedelta(seconds=3), False),
        (now - timedelta(seconds=2), False),
        (now - timedelta(seconds=1), True),
        (now, False),
    ):
        await attempts.add(
            LoginAttemptCreate(
                occurred_at=occurred_at,
                ip_address="127.0.0.1",
                email="window@example.com",
                success=success,
                reason=None if success else "invalid_credentials",
            )
        )

    assert (
        await attempts.count_recent_failures(
            "window@example.com",
            since=now - timedelta(minutes=15),
        )
        == 1
    )


async def test_cleanup_is_bounded_and_emits_an_event(
    account_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    user_id = await create_user(account_session, email="cleanup@example.com")
    now = datetime.now(UTC)
    account_session.add_all(
        [
            PasswordResetTokenModel(
                user_id=user_id,
                token_hash="d" * 64,
                expires_at=now - timedelta(minutes=1),
            ),
            EmailVerificationTokenModel(
                user_id=user_id,
                token_hash="e" * 64,
                expires_at=now - timedelta(minutes=1),
            ),
        ]
    )
    await account_session.flush()
    await SqlAlchemyUserRepository(account_session).set_lock(
        user_id,
        locked_until=now - timedelta(seconds=1),
        reason="expired_test_lock",
    )
    cleanup = AccountSecurityCleanupService(
        account_session,
        SqlAlchemyUserRepository(account_session),
        SqlAlchemyPasswordResetTokenRepository(account_session),
        SqlAlchemyEmailVerificationTokenRepository(account_session),
        events,
        batch_size=1,
    )

    result = await cleanup.run()

    assert result.reset_tokens_deleted == 1
    assert result.verification_tokens_deleted == 1
    assert result.accounts_unlocked == 1
    assert any(
        isinstance(event, AccountSecurityCleanupCompleted) for event in events.events
    )


def test_account_security_schema_and_indexes_are_explicit() -> None:
    user_table = UserModel.metadata.tables["identity_users"]
    reset_table = UserModel.metadata.tables["identity_password_reset_tokens"]
    verification_table = UserModel.metadata.tables["identity_email_verification_tokens"]
    assert {"locked_until", "lock_reason", "unlock_count"} <= set(
        user_table.columns.keys()
    )
    assert "ck_identity_users_unlock_count_nonnegative" in {
        constraint.name for constraint in user_table.constraints
    }
    assert "ix_identity_users_locked_until" in {
        index.name for index in user_table.indexes
    }
    assert "ix_identity_password_reset_tokens_expiry_cleanup" in {
        index.name for index in reset_table.indexes
    }
    assert "ix_identity_email_verification_tokens_expiry_cleanup" in {
        index.name for index in verification_table.indexes
    }


def test_account_security_routes_openapi_rate_limits_and_metrics(
    test_settings: Settings,
) -> None:
    schema = create_application(test_settings).openapi()
    paths = {
        "/api/v1/account/password/change",
        "/api/v1/account/password/forgot",
        "/api/v1/account/password/reset",
        "/api/v1/account/email/verify",
        "/api/v1/account/email/resend",
    }
    assert paths <= set(schema["paths"])
    assert schema["paths"]["/api/v1/account/password/change"]["post"]["security"]
    for path in paths - {"/api/v1/account/password/change"}:
        assert (
            authentication_rate_limit_scope({"type": "http", "path": path})
            == RateLimitScope.PASSWORD_RESET
        )
    assert all(
        metric is not None
        for metric in (
            PASSWORD_CHANGES,
            PASSWORD_RESETS,
            EMAIL_VERIFICATIONS,
            ACCOUNT_LOCKOUTS,
            SECURITY_EVENTS,
            ACCOUNT_SECURITY_CLEANUP_EXECUTIONS,
        )
    )
