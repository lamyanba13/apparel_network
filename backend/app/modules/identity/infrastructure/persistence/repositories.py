from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.application.schemas import (
    EmailVerificationTokenCreate,
    EmailVerificationTokenRecord,
    LoginAttemptCreate,
    LoginAttemptRecord,
    PasswordHistoryCreate,
    PasswordHistoryRecord,
    PasswordResetTokenCreate,
    PasswordResetTokenRecord,
    PermissionCreate,
    PermissionRecord,
    RefreshSessionCreate,
    RefreshSessionRecord,
    RoleCreate,
    RolePermissionCreate,
    RolePermissionRecord,
    RoleRecord,
    UserCreate,
    UserRecord,
    UserRoleCreate,
    UserRoleRecord,
)
from app.modules.identity.domain import normalize_email
from app.modules.identity.infrastructure.persistence.models import (
    EmailVerificationTokenModel,
    LoginAttemptModel,
    PasswordHistoryModel,
    PasswordResetTokenModel,
    PermissionModel,
    RefreshSessionModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
    UserRoleModel,
)


class SqlAlchemyRepository:
    """Session-bound base that deliberately owns no transaction commit."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session


async def _persist_model(
    session: AsyncSession,
    model: object,
) -> None:
    session.add(model)
    await session.flush()
    await session.refresh(model)


class SqlAlchemyUserRepository(SqlAlchemyRepository):
    async def add(self, values: UserCreate) -> UserRecord:
        model = UserModel(
            email=values.email,
            normalized_email=values.normalized_email,
            display_name=values.display_name,
            password_hash=values.password_hash.get_secret_value(),
            is_email_verified=values.is_email_verified,
            email_verified_at=values.email_verified_at,
            is_active=values.is_active,
            is_locked=values.is_locked,
            deleted_at=values.deleted_at,
            created_by_id=values.created_by_id,
            updated_by_id=values.updated_by_id,
        )
        await _persist_model(self._session, model)
        return UserRecord.model_validate(model)

    async def get_by_id(
        self,
        user_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> UserRecord | None:
        statement = select(UserModel).where(UserModel.id == user_id)
        if not include_deleted:
            statement = statement.where(UserModel.deleted_at.is_(None))
        return await self._record_or_none(statement)

    async def get_by_email(
        self,
        email: str,
        *,
        include_deleted: bool = False,
    ) -> UserRecord | None:
        statement = select(UserModel).where(
            UserModel.normalized_email == normalize_email(email)
        )
        if not include_deleted:
            statement = statement.where(UserModel.deleted_at.is_(None))
        return await self._record_or_none(statement)

    async def _record_or_none(
        self,
        statement: Select[tuple[UserModel]],
    ) -> UserRecord | None:
        model = await self._session.scalar(statement)
        return UserRecord.model_validate(model) if model is not None else None


class SqlAlchemyRoleRepository(SqlAlchemyRepository):
    async def add(self, values: RoleCreate) -> RoleRecord:
        model = RoleModel(**values.model_dump())
        await _persist_model(self._session, model)
        return RoleRecord.model_validate(model)

    async def get_by_name(self, name: str) -> RoleRecord | None:
        model = await self._session.scalar(
            select(RoleModel).where(RoleModel.name == name.strip())
        )
        return RoleRecord.model_validate(model) if model is not None else None


class SqlAlchemyPermissionRepository(SqlAlchemyRepository):
    async def add(self, values: PermissionCreate) -> PermissionRecord:
        model = PermissionModel(**values.model_dump())
        await _persist_model(self._session, model)
        return PermissionRecord.model_validate(model)

    async def get_by_name(self, name: str) -> PermissionRecord | None:
        model = await self._session.scalar(
            select(PermissionModel).where(PermissionModel.name == name.strip())
        )
        return PermissionRecord.model_validate(model) if model is not None else None


class SqlAlchemyIdentityGrantRepository(SqlAlchemyRepository):
    async def add_user_role(self, values: UserRoleCreate) -> UserRoleRecord:
        model = UserRoleModel(**values.model_dump())
        await _persist_model(self._session, model)
        return UserRoleRecord.model_validate(model)

    async def add_role_permission(
        self,
        values: RolePermissionCreate,
    ) -> RolePermissionRecord:
        model = RolePermissionModel(**values.model_dump())
        await _persist_model(self._session, model)
        return RolePermissionRecord.model_validate(model)


class SqlAlchemyRefreshSessionRepository(SqlAlchemyRepository):
    async def add(self, values: RefreshSessionCreate) -> RefreshSessionRecord:
        model = RefreshSessionModel(
            **values.model_dump(
                exclude={"refresh_token_hash", "ip_address"},
            ),
            refresh_token_hash=values.refresh_token_hash.get_secret_value(),
            ip_address=str(values.ip_address),
        )
        await _persist_model(self._session, model)
        return RefreshSessionRecord.model_validate(model)

    async def get_by_token_hash(
        self,
        token_hash: str,
    ) -> RefreshSessionRecord | None:
        model = await self._session.scalar(
            select(RefreshSessionModel).where(
                RefreshSessionModel.refresh_token_hash == token_hash
            )
        )
        return RefreshSessionRecord.model_validate(model) if model is not None else None


class SqlAlchemyPasswordHistoryRepository(SqlAlchemyRepository):
    async def add(
        self,
        values: PasswordHistoryCreate,
    ) -> PasswordHistoryRecord:
        model = PasswordHistoryModel(
            user_id=values.user_id,
            password_hash=values.password_hash.get_secret_value(),
        )
        await _persist_model(self._session, model)
        return PasswordHistoryRecord.model_validate(model)

    async def list_recent(
        self,
        user_id: UUID,
        *,
        limit: int,
    ) -> Sequence[PasswordHistoryRecord]:
        if not 1 <= limit <= 100:
            raise ValueError("password history limit must be between 1 and 100")
        models = (
            await self._session.scalars(
                select(PasswordHistoryModel)
                .where(PasswordHistoryModel.user_id == user_id)
                .order_by(
                    PasswordHistoryModel.created_at.desc(),
                    PasswordHistoryModel.id.desc(),
                )
                .limit(limit)
            )
        ).all()
        return tuple(PasswordHistoryRecord.model_validate(model) for model in models)


class SqlAlchemyLoginAttemptRepository(SqlAlchemyRepository):
    async def add(self, values: LoginAttemptCreate) -> LoginAttemptRecord:
        model = LoginAttemptModel(
            **values.model_dump(exclude={"ip_address"}),
            ip_address=str(values.ip_address),
        )
        await _persist_model(self._session, model)
        return LoginAttemptRecord.model_validate(model)


class SqlAlchemyEmailVerificationTokenRepository(SqlAlchemyRepository):
    async def add(
        self,
        values: EmailVerificationTokenCreate,
    ) -> EmailVerificationTokenRecord:
        model = EmailVerificationTokenModel(
            **values.model_dump(exclude={"token_hash"}),
            token_hash=values.token_hash.get_secret_value(),
        )
        await _persist_model(self._session, model)
        return EmailVerificationTokenRecord.model_validate(model)

    async def get_by_hash(
        self,
        token_hash: str,
    ) -> EmailVerificationTokenRecord | None:
        model = await self._session.scalar(
            select(EmailVerificationTokenModel).where(
                EmailVerificationTokenModel.token_hash == token_hash
            )
        )
        return (
            EmailVerificationTokenRecord.model_validate(model)
            if model is not None
            else None
        )


class SqlAlchemyPasswordResetTokenRepository(SqlAlchemyRepository):
    async def add(
        self,
        values: PasswordResetTokenCreate,
    ) -> PasswordResetTokenRecord:
        model = PasswordResetTokenModel(
            **values.model_dump(exclude={"token_hash"}),
            token_hash=values.token_hash.get_secret_value(),
        )
        await _persist_model(self._session, model)
        return PasswordResetTokenRecord.model_validate(model)

    async def get_by_hash(
        self,
        token_hash: str,
    ) -> PasswordResetTokenRecord | None:
        model = await self._session.scalar(
            select(PasswordResetTokenModel).where(
                PasswordResetTokenModel.token_hash == token_hash
            )
        )
        return (
            PasswordResetTokenRecord.model_validate(model)
            if model is not None
            else None
        )
