from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Protocol
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.common.context import maybe_get_request_context
from app.common.errors import ErrorCode
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.identity.application.repositories import (
    LoginAttemptRepository,
    RefreshSessionRepository,
    UserRepository,
)
from app.modules.identity.application.schemas import (
    LoginAttemptCreate,
    RefreshSessionCreate,
    RefreshSessionRecord,
    UserRecord,
)
from app.modules.identity.domain import (
    AuthenticationFailed,
    AuthenticationSucceeded,
    LogoutCompleted,
    RefreshReuseDetected,
    RefreshRotated,
    parse_device,
)
from app.modules.identity.domain.session_events import SessionCreated

_INVALID_CREDENTIALS = "Invalid email or password."
_INVALID_REFRESH_TOKEN = "Invalid refresh token."


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    version: int
    subject: UUID
    session_id: UUID
    token_id: UUID
    issued_at: datetime
    not_before: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthenticationTokens:
    access_token: str
    refresh_token: SecretStr
    expires_in: int
    token_type: str = "Bearer"


@dataclass(frozen=True, slots=True)
class AuthenticationContext:
    ip_address: IPv4Address | IPv6Address
    user_agent: str
    device_name: str
    browser: str
    operating_system: str
    device_type: str
    platform: str


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    user: UserRecord
    session: RefreshSessionRecord
    claims: AccessTokenClaims


class PasswordService(Protocol):
    def hash_password(self, password: SecretStr) -> str: ...

    def verify_password(self, password: SecretStr, password_hash: str) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool: ...

    def verify_dummy(self, password: SecretStr) -> None: ...


class TokenService(Protocol):
    @property
    def access_token_lifetime_seconds(self) -> int: ...

    def create_access_token(self, *, user_id: UUID, session_id: UUID) -> str: ...

    def decode_access_token(self, token: str) -> AccessTokenClaims: ...

    def generate_refresh_token(self) -> SecretStr: ...

    def hash_refresh_token(self, token: SecretStr | str) -> str: ...


class LoginSecurityService(Protocol):
    async def before_attempt(
        self,
        user: UserRecord | None,
        *,
        now: datetime,
    ) -> None: ...

    async def after_failure(
        self,
        user: UserRecord | None,
        *,
        email: str,
        now: datetime,
    ) -> None: ...

    async def after_success(
        self,
        user: UserRecord,
        *,
        now: datetime,
    ) -> None: ...


class SessionService:
    """Application service for opaque refresh-session lifecycle."""

    def __init__(
        self,
        repository: RefreshSessionRepository,
        token_service: TokenService,
        event_publisher: EventPublisher,
        *,
        refresh_lifetime: timedelta,
    ) -> None:
        self._repository = repository
        self._token_service = token_service
        self._event_publisher = event_publisher
        self._refresh_lifetime = refresh_lifetime

    async def create(
        self,
        *,
        user_id: UUID,
        context: AuthenticationContext,
    ) -> tuple[RefreshSessionRecord, SecretStr]:
        refresh_token = self._token_service.generate_refresh_token()
        now = datetime.now(UTC)
        display_name = context.device_name
        session = await self._repository.add(
            RefreshSessionCreate(
                user_id=user_id,
                refresh_token_hash=self._token_service.hash_refresh_token(
                    refresh_token
                ),
                family_id=uuid7(),
                device_name=context.device_name,
                display_name=display_name,
                browser=context.browser,
                operating_system=context.operating_system,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                last_activity_at=now,
                last_seen_at=now,
                last_ip=context.ip_address,
                last_user_agent=context.user_agent,
                last_browser=context.browser,
                last_operating_system=context.operating_system,
                last_device_type=context.device_type,
                platform=context.platform,
                expires_at=now + self._refresh_lifetime,
            )
        )
        return session, refresh_token

    async def rotate(
        self,
        refresh_token: SecretStr,
    ) -> tuple[RefreshSessionRecord, SecretStr] | None:
        token_hash = self._token_service.hash_refresh_token(refresh_token)
        current = await self._repository.get_by_token_hash(
            token_hash,
            for_update=True,
        )
        if current is None:
            return None
        if current.is_revoked:
            await self._repository.revoke_family(current.family_id)
            await self._event_publisher.publish(
                RefreshReuseDetected(
                    user_id=current.user_id,
                    session_id=current.id,
                    family_id=current.family_id,
                    correlation_id=_correlation_id(),
                )
            )
            return None

        now = datetime.now(UTC)
        if current.expires_at <= now:
            await self._repository.revoke(current.id)
            return None

        next_token = self._token_service.generate_refresh_token()
        await self._repository.revoke(current.id)
        child = await self._repository.add(
            RefreshSessionCreate(
                user_id=current.user_id,
                refresh_token_hash=self._token_service.hash_refresh_token(next_token),
                family_id=current.family_id,
                parent_session_id=current.id,
                rotation_count=current.rotation_count + 1,
                risk_score=current.risk_score,
                last_country=current.last_country,
                last_asn=current.last_asn,
                last_device_fingerprint=current.last_device_fingerprint,
                device_name=current.device_name,
                display_name=current.display_name,
                browser=current.browser,
                operating_system=current.operating_system,
                ip_address=current.ip_address,
                user_agent=current.user_agent,
                last_activity_at=now,
                last_seen_at=now,
                last_ip=current.last_ip,
                last_user_agent=current.last_user_agent,
                last_browser=current.last_browser,
                last_operating_system=current.last_operating_system,
                last_device_type=current.last_device_type,
                platform=current.platform,
                city=current.city,
                is_trusted=current.is_trusted,
                expires_at=current.expires_at,
            )
        )
        return child, next_token

    async def revoke(self, session_id: UUID) -> bool:
        return await self._repository.revoke(session_id)

    async def revoke_all(self, user_id: UUID) -> int:
        return await self._repository.revoke_all_for_user(user_id)


class AuthenticationService:
    """Authenticate credentials and coordinate tokens without authorization."""

    def __init__(
        self,
        session: AsyncSession,
        users: UserRepository,
        login_attempts: LoginAttemptRepository,
        sessions: SessionService,
        session_repository: RefreshSessionRepository,
        password_service: PasswordService,
        token_service: TokenService,
        event_publisher: EventPublisher,
        *,
        require_verified_email: bool,
        login_security: LoginSecurityService | None = None,
    ) -> None:
        self._db_session = session
        self._users = users
        self._login_attempts = login_attempts
        self._sessions = sessions
        self._session_repository = session_repository
        self._password_service = password_service
        self._token_service = token_service
        self._event_publisher = event_publisher
        self._require_verified_email = require_verified_email
        self._login_security = login_security

    async def login(
        self,
        *,
        email: str,
        password: SecretStr,
        context: AuthenticationContext,
    ) -> AuthenticationTokens:
        authenticated: tuple[UserRecord, RefreshSessionRecord, SecretStr] | None = None
        async with _transaction(self._db_session):
            user = await self._users.get_by_email(email, include_deleted=True)
            now = datetime.now(UTC)
            if self._login_security is not None:
                await self._login_security.before_attempt(user, now=now)
            password_valid = self._verify_candidate(password, user)
            account_eligible = user is not None and self._account_is_eligible(
                user,
                now=now,
            )
            success = password_valid and account_eligible
            await self._login_attempts.add(
                LoginAttemptCreate(
                    occurred_at=now,
                    ip_address=context.ip_address,
                    email=email,
                    success=success,
                    reason=None if success else "invalid_credentials",
                )
            )
            if self._login_security is not None:
                if success and user is not None:
                    await self._login_security.after_success(user, now=now)
                else:
                    await self._login_security.after_failure(
                        user,
                        email=email,
                        now=now,
                    )
            if success and user is not None:
                session, refresh_token = await self._sessions.create(
                    user_id=user.id,
                    context=context,
                )
                authenticated = (user, session, refresh_token)

        if authenticated is None:
            await self._event_publisher.publish(
                AuthenticationFailed(correlation_id=_correlation_id())
            )
            raise _authentication_error(_INVALID_CREDENTIALS)

        user, session, refresh_token = authenticated
        await self._event_publisher.publish(
            AuthenticationSucceeded(
                user_id=user.id,
                session_id=session.id,
                correlation_id=_correlation_id(),
            )
        )
        await self._event_publisher.publish(
            SessionCreated(
                user_id=user.id,
                session_id=session.id,
                correlation_id=_correlation_id(),
            )
        )
        return self._tokens(user.id, session.id, refresh_token)

    async def refresh(self, refresh_token: SecretStr) -> AuthenticationTokens:
        rotated: tuple[RefreshSessionRecord, SecretStr] | None
        async with _transaction(self._db_session):
            rotated = await self._sessions.rotate(refresh_token)
            if rotated is not None:
                session, _ = rotated
                user = await self._users.get_by_id(
                    session.user_id,
                    include_deleted=True,
                )
                if user is None or not self._account_is_eligible(
                    user,
                    now=datetime.now(UTC),
                ):
                    await self._sessions.revoke_all(session.user_id)
                    rotated = None

        if rotated is None:
            raise _authentication_error(_INVALID_REFRESH_TOKEN)
        session, next_token = rotated
        await self._event_publisher.publish(
            RefreshRotated(
                user_id=session.user_id,
                session_id=session.id,
                family_id=session.family_id,
                rotation_count=session.rotation_count,
                correlation_id=_correlation_id(),
            )
        )
        return self._tokens(session.user_id, session.id, next_token)

    async def authenticate_access_token(self, token: str) -> AuthenticatedIdentity:
        claims = self._token_service.decode_access_token(token)
        session = await self._session_repository.get_by_id(claims.session_id)
        user = await self._users.get_by_id(claims.subject, include_deleted=True)
        now = datetime.now(UTC)
        if (
            session is None
            or user is None
            or session.user_id != claims.subject
            or session.is_revoked
            or session.expires_at <= now
            or not self._account_is_eligible(user, now=now)
        ):
            raise _authentication_error("Authentication credentials are invalid.")
        return AuthenticatedIdentity(user=user, session=session, claims=claims)

    async def logout(self, session_id: UUID) -> None:
        async with _transaction(self._db_session):
            await self._sessions.revoke(session_id)
        await self._event_publisher.publish(
            LogoutCompleted(
                session_id=session_id,
                correlation_id=_correlation_id(),
            )
        )

    async def logout_all(self, user_id: UUID) -> int:
        async with _transaction(self._db_session):
            count = await self._sessions.revoke_all(user_id)
        await self._event_publisher.publish(
            LogoutCompleted(
                user_id=user_id,
                revoked_sessions=count,
                correlation_id=_correlation_id(),
            )
        )
        return count

    def _verify_candidate(
        self,
        password: SecretStr,
        user: UserRecord | None,
    ) -> bool:
        if user is None:
            self._password_service.verify_dummy(password)
            return False
        return self._password_service.verify_password(
            password,
            user.password_hash.get_secret_value(),
        )

    def _account_is_eligible(
        self,
        user: UserRecord,
        *,
        now: datetime,
    ) -> bool:
        lock_active = user.is_locked and (
            user.locked_until is None or user.locked_until > now
        )
        return (
            user.is_active
            and not lock_active
            and user.deleted_at is None
            and (user.is_email_verified or not self._require_verified_email)
        )

    def _tokens(
        self,
        user_id: UUID,
        session_id: UUID,
        refresh_token: SecretStr,
    ) -> AuthenticationTokens:
        return AuthenticationTokens(
            access_token=self._token_service.create_access_token(
                user_id=user_id,
                session_id=session_id,
            ),
            refresh_token=refresh_token,
            expires_in=self._token_service.access_token_lifetime_seconds,
        )


def authentication_context(
    *,
    client_ip: str | None,
    user_agent: str | None,
    device_name: str | None,
) -> AuthenticationContext:
    try:
        parsed_ip = ip_address(client_ip or "0.0.0.0")
    except ValueError:
        parsed_ip = ip_address("0.0.0.0")
    normalized_user_agent = (user_agent or "Unknown user agent")[:1024]
    device = parse_device(normalized_user_agent)
    return AuthenticationContext(
        ip_address=parsed_ip,
        user_agent=normalized_user_agent,
        device_name=(device_name or "Unknown device")[:120],
        browser=device.browser,
        operating_system=device.operating_system,
        device_type=device.device_type,
        platform=device.platform,
    )


def _authentication_error(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.UNAUTHORIZED,
        title="Authentication failed",
        detail=detail,
        status_code=HTTPStatus.UNAUTHORIZED,
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
