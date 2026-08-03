from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from uuid import UUID

import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.modules.identity.api.dependencies import current_identity_dependency
from app.modules.identity.application.schemas import (
    RefreshSessionCreate,
    RefreshSessionRecord,
    UserCreate,
    UserRecord,
)
from app.modules.identity.application.services import (
    AccessTokenClaims,
    AuthenticatedIdentity,
)
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyRefreshSessionRepository,
    SqlAlchemyUserRepository,
)
from app.modules.identity.infrastructure.security import PwdlibPasswordService
from tests.helpers.builders import deterministic_timestamp, email


async def create_user(session: AsyncSession, value: int = 1) -> UserRecord:
    password_hash = PwdlibPasswordService().hash_password(SecretStr("ValidPass1!"))
    return await SqlAlchemyUserRepository(session).add(
        UserCreate(
            email=email(value),
            display_name=f"Test User {value}",
            password_hash=SecretStr(password_hash),
            is_email_verified=True,
            email_verified_at=deterministic_timestamp(),
        )
    )


async def create_refresh_session(
    session: AsyncSession,
    user_id: UUID,
) -> RefreshSessionRecord:
    now = deterministic_timestamp()
    return await SqlAlchemyRefreshSessionRepository(session).add(
        RefreshSessionCreate(
            user_id=user_id,
            refresh_token_hash=SecretStr("0" * 64),
            family_id=uuid7(),
            device_name="Integration test device",
            display_name="Integration test device",
            ip_address=ip_address("127.0.0.1"),
            user_agent="fashion-network-test",
            last_activity_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=1),
        )
    )


@pytest.fixture
async def identity_user(db_session: AsyncSession) -> UserRecord:
    return await create_user(db_session)


@pytest.fixture
async def refresh_session(
    db_session: AsyncSession,
    identity_user: UserRecord,
) -> RefreshSessionRecord:
    return await create_refresh_session(db_session, identity_user.id)


@pytest.fixture
async def authenticated_identity(
    identity_user: UserRecord,
    refresh_session: RefreshSessionRecord,
) -> AuthenticatedIdentity:
    now = datetime.now(UTC)
    return AuthenticatedIdentity(
        identity_user,
        refresh_session,
        AccessTokenClaims(
            1,
            identity_user.id,
            refresh_session.id,
            uuid7(),
            now,
            now,
            now + timedelta(minutes=15),
        ),
    )


@pytest.fixture
def authenticated_identity_override(
    application: FastAPI,
    authenticated_identity: AuthenticatedIdentity,
) -> AuthenticatedIdentity:
    application.dependency_overrides[current_identity_dependency] = (
        lambda: authenticated_identity
    )
    return authenticated_identity
