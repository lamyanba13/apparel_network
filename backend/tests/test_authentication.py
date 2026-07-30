from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.common.config import Settings, get_settings
from app.common.events import DomainEvent, EventPublisher
from app.common.exceptions import AppError
from app.common.middleware.rate_limit import authentication_rate_limit_scope
from app.common.rate_limiting import RateLimitScope
from app.main import create_application
from app.modules.identity.application.schemas import UserCreate
from app.modules.identity.application.services import (
    AuthenticationService,
    SessionService,
    authentication_context,
)
from app.modules.identity.domain import (
    AuthenticationFailed,
    AuthenticationSucceeded,
    LogoutCompleted,
    RefreshReuseDetected,
    RefreshRotated,
)
from app.modules.identity.domain.session_events import SessionCreated
from app.modules.identity.infrastructure.events import AuthenticationEventPublisher
from app.modules.identity.infrastructure.persistence.models import (
    LoginAttemptModel,
    RefreshSessionModel,
)
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyLoginAttemptRepository,
    SqlAlchemyRefreshSessionRepository,
    SqlAlchemyUserRepository,
)
from app.modules.identity.infrastructure.security import (
    JwtTokenService,
    PwdlibPasswordService,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PASSWORD = SecretStr("Correct horse battery staple")


@dataclass
class RecordingEventPublisher:
    events: list[DomainEvent] = field(default_factory=list)

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


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
async def auth_session(
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


def make_service(
    session: AsyncSession,
    settings: Settings,
    event_publisher: EventPublisher | None = None,
) -> AuthenticationService:
    token_service = JwtTokenService(settings)
    password_service = PwdlibPasswordService()
    session_repository = SqlAlchemyRefreshSessionRepository(session)
    events = event_publisher or AuthenticationEventPublisher()
    return AuthenticationService(
        session,
        SqlAlchemyUserRepository(session),
        SqlAlchemyLoginAttemptRepository(session),
        SessionService(
            session_repository,
            token_service,
            events,
            refresh_lifetime=timedelta(days=settings.auth_refresh_token_lifetime_days),
        ),
        session_repository,
        password_service,
        token_service,
        events,
        require_verified_email=settings.auth_require_verified_email,
    )


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password_service: PwdlibPasswordService,
    is_active: bool = True,
    is_locked: bool = False,
    is_verified: bool = True,
    deleted_at: datetime | None = None,
) -> UUID:
    async with session.begin():
        record = await SqlAlchemyUserRepository(session).add(
            UserCreate(
                email=email,
                display_name="Authentication Test",
                password_hash=password_service.hash_password(PASSWORD),
                is_email_verified=is_verified,
                email_verified_at=datetime.now(UTC) if is_verified else None,
                is_active=is_active,
                is_locked=is_locked,
                deleted_at=deleted_at,
            )
        )
    return record.id


def context() -> object:
    return authentication_context(
        client_ip="127.0.0.1",
        user_agent="Authentication test agent",
        device_name="Test device",
    )


def public_key(private_key_pem: str) -> str:
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(),
        password=None,
    )
    return (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


def test_password_service_uses_argon2id_and_verifies() -> None:
    service = PwdlibPasswordService()
    password_hash = service.hash_password(PASSWORD)

    assert password_hash.startswith("$argon2id$")
    assert service.verify_password(PASSWORD, password_hash)
    assert not service.verify_password(SecretStr("wrong password"), password_hash)
    assert not service.needs_rehash(password_hash)
    assert service.needs_rehash("invalid-hash")


def test_access_token_contains_only_approved_identity_claims(
    test_settings: Settings,
) -> None:
    service = JwtTokenService(test_settings)
    token = service.create_access_token(user_id=UUID(int=1), session_id=UUID(int=2))
    claims = jwt.decode(token, options={"verify_signature": False})

    assert set(claims) == {
        "ver",
        "sub",
        "sid",
        "jti",
        "iss",
        "aud",
        "iat",
        "nbf",
        "exp",
        "type",
    }
    assert claims["type"] == "access"
    assert claims["ver"] == 1
    assert claims["exp"] - claims["iat"] == 900
    assert jwt.get_unverified_header(token)["alg"] == "EdDSA"
    assert jwt.get_unverified_header(token)["kid"] == "primary"


def test_tampered_and_expired_access_tokens_are_rejected(
    test_settings: Settings,
) -> None:
    service = JwtTokenService(test_settings)
    token = service.create_access_token(user_id=UUID(int=1), session_id=UUID(int=2))
    payload, signature = token.rsplit(".", maxsplit=1)
    tampered = f"{payload}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"

    with pytest.raises(AppError):
        service.decode_access_token(tampered)

    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "ver": 1,
            "sub": str(UUID(int=1)),
            "sid": str(UUID(int=2)),
            "jti": str(UUID(int=3)),
            "iss": test_settings.jwt_issuer,
            "aud": test_settings.jwt_audience,
            "iat": now - timedelta(minutes=20),
            "nbf": now - timedelta(minutes=20),
            "exp": now - timedelta(minutes=5),
            "type": "access",
        },
        test_settings.jwt_private_key_pem.get_secret_value(),  # type: ignore[union-attr]
        algorithm="EdDSA",
        headers={"kid": test_settings.jwt_current_key_id},
    )
    with pytest.raises(AppError):
        service.decode_access_token(expired)


def test_previous_public_key_validates_tokens_during_rotation(
    test_settings: Settings,
    test_private_key_pem: str,
) -> None:
    old_settings = test_settings.model_copy(
        update={
            "jwt_current_key_id": "old",
            "jwt_private_key_pem": SecretStr(test_private_key_pem),
        }
    )
    old_service = JwtTokenService(old_settings)
    token = old_service.create_access_token(
        user_id=UUID(int=10),
        session_id=UUID(int=11),
    )
    new_private_key = (
        Ed25519PrivateKey.generate()
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode()
    )
    new_settings = test_settings.model_copy(
        update={
            "jwt_current_key_id": "new",
            "jwt_private_key_pem": SecretStr(new_private_key),
            "jwt_previous_public_keys": {"old": public_key(test_private_key_pem)},
        }
    )

    claims = JwtTokenService(new_settings).decode_access_token(token)

    assert claims.subject == UUID(int=10)
    assert claims.session_id == UUID(int=11)


def test_access_token_contains_identity_claims_only(
    test_settings: Settings,
) -> None:
    token = JwtTokenService(test_settings).create_access_token(
        user_id=UUID(int=20),
        session_id=UUID(int=21),
    )
    unverified = jwt.decode(
        token,
        options={"verify_signature": False},
    )

    assert set(unverified) == {
        "ver",
        "sub",
        "sid",
        "jti",
        "iss",
        "aud",
        "iat",
        "nbf",
        "exp",
        "type",
    }
    assert "roles" not in unverified
    assert "permissions" not in unverified


async def test_login_creates_hashed_session_and_valid_access_token(
    auth_session: AsyncSession,
    test_settings: Settings,
) -> None:
    passwords = PwdlibPasswordService()
    user_id = await create_user(
        auth_session,
        email="login@example.com",
        password_service=passwords,
    )
    service = make_service(auth_session, test_settings)

    tokens = await service.login(
        email=" LOGIN@EXAMPLE.COM ",
        password=PASSWORD,
        context=context(),  # type: ignore[arg-type]
    )
    claims = JwtTokenService(test_settings).decode_access_token(tokens.access_token)
    session = await auth_session.get(RefreshSessionModel, claims.session_id)

    assert claims.subject == user_id
    assert session is not None
    assert session.refresh_token_hash != tokens.refresh_token.get_secret_value()
    assert len(session.refresh_token_hash) == 64
    assert session.family_id is not None
    assert session.rotation_count == 0


@pytest.mark.parametrize(
    ("email", "user_kwargs"),
    [
        ("missing@example.com", None),
        ("inactive@example.com", {"is_active": False}),
        ("locked@example.com", {"is_locked": True}),
        (
            "deleted@example.com",
            {"is_active": False, "deleted_at": datetime.now(UTC)},
        ),
        ("unverified@example.com", {"is_verified": False}),
    ],
)
async def test_login_failures_use_one_generic_message(
    auth_session: AsyncSession,
    test_settings: Settings,
    email: str,
    user_kwargs: dict[str, object] | None,
) -> None:
    passwords = PwdlibPasswordService()
    if user_kwargs is not None:
        await create_user(
            auth_session,
            email=email,
            password_service=passwords,
            **user_kwargs,  # type: ignore[arg-type]
        )
    service = make_service(auth_session, test_settings)

    with pytest.raises(AppError) as captured:
        await service.login(
            email=email,
            password=PASSWORD,
            context=context(),  # type: ignore[arg-type]
        )

    assert captured.value.detail == "Invalid email or password."
    attempt = await auth_session.scalar(
        select(LoginAttemptModel)
        .where(LoginAttemptModel.email == email)
        .order_by(LoginAttemptModel.occurred_at.desc())
    )
    assert attempt is not None
    assert not attempt.success
    assert attempt.reason == "invalid_credentials"


async def test_refresh_rotates_and_reuse_revokes_the_family(
    auth_session: AsyncSession,
    test_settings: Settings,
) -> None:
    passwords = PwdlibPasswordService()
    await create_user(
        auth_session,
        email="rotation@example.com",
        password_service=passwords,
    )
    service = make_service(auth_session, test_settings)
    initial = await service.login(
        email="rotation@example.com",
        password=PASSWORD,
        context=context(),  # type: ignore[arg-type]
    )

    rotated = await service.refresh(initial.refresh_token)
    assert (
        rotated.refresh_token.get_secret_value()
        != initial.refresh_token.get_secret_value()
    )

    with pytest.raises(AppError):
        await service.refresh(initial.refresh_token)
    with pytest.raises(AppError):
        await service.refresh(rotated.refresh_token)

    sessions = (
        await auth_session.scalars(
            select(RefreshSessionModel).order_by(RefreshSessionModel.rotation_count)
        )
    ).all()
    assert len(sessions) == 2
    assert sessions[1].parent_session_id == sessions[0].id
    assert sessions[1].family_id == sessions[0].family_id
    assert sessions[1].rotation_count == 1
    assert all(session.is_revoked for session in sessions)


async def test_logout_and_logout_all_revoke_sessions(
    auth_session: AsyncSession,
    test_settings: Settings,
) -> None:
    passwords = PwdlibPasswordService()
    user_id = await create_user(
        auth_session,
        email="logout@example.com",
        password_service=passwords,
    )
    service = make_service(auth_session, test_settings)
    first = await service.login(
        email="logout@example.com",
        password=PASSWORD,
        context=context(),  # type: ignore[arg-type]
    )
    second = await service.login(
        email="logout@example.com",
        password=PASSWORD,
        context=context(),  # type: ignore[arg-type]
    )
    first_claims = JwtTokenService(test_settings).decode_access_token(
        first.access_token
    )

    await service.logout(first_claims.session_id)
    with pytest.raises(AppError):
        await service.authenticate_access_token(first.access_token)

    assert await service.logout_all(user_id) == 1
    with pytest.raises(AppError):
        await service.authenticate_access_token(second.access_token)


async def test_authentication_services_emit_typed_internal_events(
    auth_session: AsyncSession,
    test_settings: Settings,
) -> None:
    passwords = PwdlibPasswordService()
    await create_user(
        auth_session,
        email="events@example.com",
        password_service=passwords,
    )
    publisher = RecordingEventPublisher()
    service = make_service(auth_session, test_settings, publisher)
    initial = await service.login(
        email="events@example.com",
        password=PASSWORD,
        context=context(),  # type: ignore[arg-type]
    )
    rotated = await service.refresh(initial.refresh_token)
    with pytest.raises(AppError):
        await service.refresh(initial.refresh_token)
    claims = JwtTokenService(test_settings).decode_access_token(rotated.access_token)
    await service.logout(claims.session_id)
    with pytest.raises(AppError):
        await service.login(
            email="events@example.com",
            password=SecretStr("wrong password"),
            context=context(),  # type: ignore[arg-type]
        )

    assert any(isinstance(event, AuthenticationSucceeded) for event in publisher.events)
    assert any(isinstance(event, SessionCreated) for event in publisher.events)
    assert any(isinstance(event, RefreshRotated) for event in publisher.events)
    assert any(isinstance(event, RefreshReuseDetected) for event in publisher.events)
    assert any(isinstance(event, LogoutCompleted) for event in publisher.events)
    assert any(isinstance(event, AuthenticationFailed) for event in publisher.events)


def test_authentication_routes_and_bearer_scheme_are_in_openapi(
    test_settings: Settings,
) -> None:
    schema = create_application(test_settings).openapi()

    assert {
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/logout-all",
    } <= set(schema["paths"])
    schemes = schema["components"]["securitySchemes"]
    assert schemes["HTTPBearer"]["type"] == "http"
    assert schemes["HTTPBearer"]["scheme"] == "bearer"


def test_authentication_routes_receive_dedicated_rate_limit_scopes() -> None:
    def scope(path: str) -> dict[str, object]:
        return {"type": "http", "path": path}

    assert (
        authentication_rate_limit_scope(scope("/api/v1/auth/login"))
        == RateLimitScope.AUTH_LOGIN
    )
    assert (
        authentication_rate_limit_scope(scope("/api/v1/auth/refresh"))
        == RateLimitScope.AUTH_REFRESH
    )
    assert (
        authentication_rate_limit_scope(scope("/api/v1/account/password/reset"))
        == RateLimitScope.PASSWORD_RESET
    )
