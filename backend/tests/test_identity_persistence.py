from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.modules.identity.application.schemas import (
    EmailVerificationTokenCreate,
    LoginAttemptCreate,
    PasswordHistoryCreate,
    PasswordResetTokenCreate,
    PermissionCreate,
    RefreshSessionCreate,
    RoleCreate,
    RolePermissionCreate,
    UserCreate,
    UserRoleCreate,
)
from app.modules.identity.infrastructure.persistence.models import (
    EmailVerificationTokenModel,
    LoginAttemptModel,
    PasswordHistoryModel,
    PasswordResetTokenModel,
    RefreshSessionModel,
    RoleModel,
    UserModel,
    UserRoleModel,
)
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyEmailVerificationTokenRepository,
    SqlAlchemyIdentityGrantRepository,
    SqlAlchemyLoginAttemptRepository,
    SqlAlchemyPasswordHistoryRepository,
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemyPermissionRepository,
    SqlAlchemyRefreshSessionRepository,
    SqlAlchemyRoleRepository,
    SqlAlchemyUserRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$ZGlnaWVzdA"
OTHER_ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$b3RoZXI$ZGlnaWVzdA"
TOKEN_HASH = "a" * 64
OTHER_TOKEN_HASH = "b" * 64


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
async def identity_session(
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
        )
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()
    await engine.dispose()


def user_values(email: str = "User@Example.com") -> UserCreate:
    return UserCreate(
        email=email,
        display_name="Identity User",
        password_hash=ARGON2_HASH,
    )


def test_persistence_schemas_normalize_email_and_reject_raw_secrets() -> None:
    values = user_values("  Mixed.Case@Example.COM ")

    assert values.email == "Mixed.Case@Example.COM"
    assert values.normalized_email == "mixed.case@example.com"
    assert "argon2id" not in repr(values)

    with pytest.raises(ValidationError):
        UserCreate(
            email="user@example.com",
            display_name="Unsafe",
            password_hash="plaintext-password",
        )

    with pytest.raises(ValidationError):
        EmailVerificationTokenCreate(
            user_id=UUID(int=1),
            token_hash="raw-token",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )


async def test_user_repository_creates_uuid7_and_normalizes_before_persistence(
    identity_session: AsyncSession,
) -> None:
    repository = SqlAlchemyUserRepository(identity_session)

    record = await repository.add(user_values("  Mixed.Case@Example.COM "))

    assert record.id.version == 7
    assert record.normalized_email == "mixed.case@example.com"
    assert record.created_at.tzinfo is not None
    assert record.updated_at.tzinfo is not None
    assert record.version == 1

    persisted = await identity_session.get(UserModel, record.id)
    assert persisted is not None
    assert persisted.email == "Mixed.Case@Example.COM"
    assert persisted.normalized_email == "mixed.case@example.com"
    assert persisted.password_hash.startswith("$argon2id$")


async def test_case_insensitive_email_uniqueness_is_database_enforced(
    identity_session: AsyncSession,
) -> None:
    repository = SqlAlchemyUserRepository(identity_session)
    await repository.add(user_values("Person@Example.com"))

    with pytest.raises(IntegrityError):
        await repository.add(user_values("person@example.COM"))


async def test_user_password_hash_constraint_rejects_non_argon2id(
    identity_session: AsyncSession,
) -> None:
    identity_session.add(
        UserModel(
            email="unsafe@example.com",
            normalized_email="unsafe@example.com",
            display_name="Unsafe",
            password_hash="not-an-argon2id-hash",
        )
    )

    with pytest.raises(IntegrityError):
        await identity_session.flush()


async def test_soft_deleted_users_are_inactive_and_excluded_by_default(
    identity_session: AsyncSession,
) -> None:
    repository = SqlAlchemyUserRepository(identity_session)
    created = await repository.add(user_values())
    model = await identity_session.get(UserModel, created.id)
    assert model is not None

    model.is_active = False
    model.deleted_at = datetime.now(UTC)
    await identity_session.flush()

    assert await repository.get_by_id(created.id) is None
    deleted = await repository.get_by_id(created.id, include_deleted=True)
    assert deleted is not None
    assert deleted.deleted_at is not None


async def test_soft_delete_constraint_rejects_active_deleted_user(
    identity_session: AsyncSession,
) -> None:
    identity_session.add(
        UserModel(
            email="deleted@example.com",
            normalized_email="deleted@example.com",
            display_name="Deleted",
            password_hash=ARGON2_HASH,
            is_active=True,
            deleted_at=datetime.now(UTC),
        )
    )

    with pytest.raises(IntegrityError):
        await identity_session.flush()


async def test_role_permission_and_user_role_relationships(
    identity_session: AsyncSession,
) -> None:
    user = await SqlAlchemyUserRepository(identity_session).add(user_values())
    role = await SqlAlchemyRoleRepository(identity_session).add(
        RoleCreate(
            name="catalog_editor",
            description="Maintains catalog records",
        )
    )
    permission = await SqlAlchemyPermissionRepository(identity_session).add(
        PermissionCreate(
            name="catalog_product:write",
            description="Write catalog products",
            resource="catalog_product",
            action="write",
        )
    )
    grants = SqlAlchemyIdentityGrantRepository(identity_session)
    await grants.add_user_role(UserRoleCreate(user_id=user.id, role_id=role.id))
    await grants.add_role_permission(
        RolePermissionCreate(
            role_id=role.id,
            permission_id=permission.id,
        )
    )

    persisted_user = await identity_session.scalar(
        select(UserModel)
        .where(UserModel.id == user.id)
        .options(
            selectinload(UserModel.user_roles)
            .selectinload(UserRoleModel.role)
            .selectinload(RoleModel.role_permissions)
        )
    )
    assert persisted_user is not None
    assert [assignment.role_id for assignment in persisted_user.user_roles] == [role.id]
    assert persisted_user.user_roles[0].role.role_permissions[0].permission_id == (
        permission.id
    )


async def test_role_names_are_unique(
    identity_session: AsyncSession,
) -> None:
    roles = SqlAlchemyRoleRepository(identity_session)
    await roles.add(RoleCreate(name="test_customer"))

    with pytest.raises(IntegrityError):
        await roles.add(RoleCreate(name="test_customer"))


async def test_permission_names_are_unique(
    identity_session: AsyncSession,
) -> None:
    permissions = SqlAlchemyPermissionRepository(identity_session)
    values = PermissionCreate(
        name="catalog_product:read",
        resource="catalog_product",
        action="read",
    )
    await permissions.add(values)

    with pytest.raises(IntegrityError):
        await permissions.add(
            PermissionCreate(
                name=values.name,
                resource=values.resource,
                action="read",
            )
        )


async def test_foreign_keys_reject_unknown_user_role_assignments(
    identity_session: AsyncSession,
) -> None:
    role = await SqlAlchemyRoleRepository(identity_session).add(
        RoleCreate(name="orphan_test")
    )

    with pytest.raises(IntegrityError):
        await SqlAlchemyIdentityGrantRepository(identity_session).add_user_role(
            UserRoleCreate(user_id=UUID(int=42), role_id=role.id)
        )


async def test_sessions_and_tokens_store_only_hashes(
    identity_session: AsyncSession,
) -> None:
    user = await SqlAlchemyUserRepository(identity_session).add(user_values())
    now = datetime.now(UTC)
    session_record = await SqlAlchemyRefreshSessionRepository(identity_session).add(
        RefreshSessionCreate(
            user_id=user.id,
            refresh_token_hash=TOKEN_HASH,
            family_id=UUID(int=2),
            device_name="Personal phone",
            display_name="Personal phone",
            browser="Firefox",
            operating_system="Android",
            ip_address="127.0.0.1",
            user_agent="Synthetic test agent",
            last_activity_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=30),
        )
    )
    verification = await SqlAlchemyEmailVerificationTokenRepository(
        identity_session
    ).add(
        EmailVerificationTokenCreate(
            user_id=user.id,
            token_hash=OTHER_TOKEN_HASH,
            expires_at=now + timedelta(minutes=30),
        )
    )
    reset = await SqlAlchemyPasswordResetTokenRepository(identity_session).add(
        PasswordResetTokenCreate(
            user_id=user.id,
            token_hash="c" * 64,
            expires_at=now + timedelta(minutes=15),
        )
    )

    assert session_record.refresh_token_hash.get_secret_value() == TOKEN_HASH
    assert verification.token_hash.get_secret_value() == OTHER_TOKEN_HASH
    assert reset.token_hash.get_secret_value() == "c" * 64
    assert (
        await identity_session.scalar(select(RefreshSessionModel.refresh_token_hash))
        == TOKEN_HASH
    )
    assert (
        await identity_session.scalar(select(EmailVerificationTokenModel.token_hash))
        == OTHER_TOKEN_HASH
    )
    assert (
        await identity_session.scalar(select(PasswordResetTokenModel.token_hash))
        == "c" * 64
    )


async def test_duplicate_password_history_is_rejected(
    identity_session: AsyncSession,
) -> None:
    user = await SqlAlchemyUserRepository(identity_session).add(user_values())
    repository = SqlAlchemyPasswordHistoryRepository(identity_session)
    values = PasswordHistoryCreate(
        user_id=user.id,
        password_hash=OTHER_ARGON2_HASH,
    )
    await repository.add(values)

    with pytest.raises(IntegrityError):
        await repository.add(values)


async def test_failed_login_attempt_requires_reason(
    identity_session: AsyncSession,
) -> None:
    identity_session.add(
        LoginAttemptModel(
            occurred_at=datetime.now(UTC),
            ip_address="127.0.0.1",
            email="user@example.com",
            success=False,
            reason=None,
        )
    )

    with pytest.raises(IntegrityError):
        await identity_session.flush()


async def test_login_attempt_repository_normalizes_email(
    identity_session: AsyncSession,
) -> None:
    record = await SqlAlchemyLoginAttemptRepository(identity_session).add(
        LoginAttemptCreate(
            occurred_at=datetime.now(UTC),
            ip_address="127.0.0.1",
            email="Attempt@Example.COM",
            success=False,
            reason="invalid_credentials",
        )
    )

    assert record.email == "attempt@example.com"


def test_required_identity_indexes_are_explicit() -> None:
    expected_indexes = {
        "identity_users": {"ix_identity_users_normalized_email"},
        "identity_refresh_sessions": {
            "ix_identity_refresh_sessions_refresh_token_hash"
        },
        "identity_email_verification_tokens": {
            "ix_identity_email_verification_tokens_token_hash"
        },
        "identity_password_reset_tokens": {
            "ix_identity_password_reset_tokens_token_hash"
        },
        "identity_login_attempts": {
            "ix_identity_login_attempts_occurred_at",
            "ix_identity_login_attempts_email_occurred",
            "ix_identity_login_attempts_ip_occurred",
        },
    }

    for table_name, required_names in expected_indexes.items():
        table = UserModel.metadata.tables[table_name]
        actual_names = {index.name for index in table.indexes}
        assert required_names <= actual_names


def test_session_risk_metadata_is_nullable_and_database_constrained() -> None:
    table = RefreshSessionModel.metadata.tables["identity_refresh_sessions"]
    risk_columns = {
        "risk_score",
        "last_country",
        "last_asn",
        "last_device_fingerprint",
    }
    constraint_names = {constraint.name for constraint in table.constraints}

    assert risk_columns <= set(table.columns.keys())
    assert all(table.c[name].nullable for name in risk_columns)
    assert {
        "ck_identity_refresh_sessions_risk_score_range",
        "ck_identity_refresh_sessions_last_country_iso_alpha2",
        "ck_identity_refresh_sessions_last_asn_range",
        "ck_identity_refresh_sessions_last_device_fingerprint_length",
    } <= constraint_names


def test_all_sensitive_model_fields_are_non_plaintext_columns() -> None:
    sensitive_columns = {
        RefreshSessionModel.__table__.c.refresh_token_hash.name,
        PasswordHistoryModel.__table__.c.password_hash.name,
        EmailVerificationTokenModel.__table__.c.token_hash.name,
        PasswordResetTokenModel.__table__.c.token_hash.name,
    }

    assert sensitive_columns == {
        "password_hash",
        "refresh_token_hash",
        "token_hash",
    }
