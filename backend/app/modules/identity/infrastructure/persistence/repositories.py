from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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
from app.modules.identity.domain.authorization import AuthorizationSnapshot
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
            locked_until=values.locked_until,
            lock_reason=values.lock_reason,
            unlock_count=values.unlock_count,
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
        for_update: bool = False,
    ) -> UserRecord | None:
        statement = select(UserModel).where(UserModel.id == user_id)
        if not include_deleted:
            statement = statement.where(UserModel.deleted_at.is_(None))
        if for_update:
            statement = statement.with_for_update()
        return await self._record_or_none(statement)

    async def get_by_email(
        self,
        email: str,
        *,
        include_deleted: bool = False,
        for_update: bool = False,
    ) -> UserRecord | None:
        statement = select(UserModel).where(
            UserModel.normalized_email == normalize_email(email)
        )
        if not include_deleted:
            statement = statement.where(UserModel.deleted_at.is_(None))
        if for_update:
            statement = statement.with_for_update()
        return await self._record_or_none(statement)

    async def update_password(self, user_id: UUID, password_hash: str) -> bool:
        result = await self._session.execute(
            update(UserModel)
            .where(UserModel.id == user_id, UserModel.deleted_at.is_(None))
            .values(
                password_hash=password_hash,
                updated_at=func.now(),
                version=UserModel.version + 1,
            )
            .returning(UserModel.id)
        )
        await self._session.flush()
        return result.scalar_one_or_none() is not None

    async def mark_email_verified(self, user_id: UUID, *, at: datetime) -> bool:
        result = await self._session.execute(
            update(UserModel)
            .where(
                UserModel.id == user_id,
                UserModel.deleted_at.is_(None),
                UserModel.is_email_verified.is_(False),
            )
            .values(
                is_email_verified=True,
                email_verified_at=at,
                updated_at=func.now(),
                version=UserModel.version + 1,
            )
            .returning(UserModel.id)
        )
        await self._session.flush()
        return result.scalar_one_or_none() is not None

    async def set_lock(
        self,
        user_id: UUID,
        *,
        locked_until: datetime,
        reason: str,
    ) -> bool:
        result = await self._session.execute(
            update(UserModel)
            .where(UserModel.id == user_id, UserModel.deleted_at.is_(None))
            .values(
                is_locked=True,
                locked_until=locked_until,
                lock_reason=reason,
                updated_at=func.now(),
                version=UserModel.version + 1,
            )
            .returning(UserModel.id)
        )
        await self._session.flush()
        return result.scalar_one_or_none() is not None

    async def unlock(self, user_id: UUID) -> bool:
        result = await self._session.execute(
            update(UserModel)
            .where(UserModel.id == user_id, UserModel.is_locked.is_(True))
            .values(
                is_locked=False,
                locked_until=None,
                lock_reason=None,
                unlock_count=UserModel.unlock_count + 1,
                updated_at=func.now(),
                version=UserModel.version + 1,
            )
            .returning(UserModel.id)
        )
        await self._session.flush()
        return result.scalar_one_or_none() is not None

    async def unlock_expired(self, *, now: datetime, limit: int) -> Sequence[UUID]:
        candidate_ids = (
            select(UserModel.id)
            .where(
                UserModel.is_locked.is_(True),
                UserModel.locked_until.is_not(None),
                UserModel.locked_until <= now,
            )
            .order_by(UserModel.locked_until, UserModel.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(
            update(UserModel)
            .where(UserModel.id.in_(candidate_ids))
            .values(
                is_locked=False,
                locked_until=None,
                lock_reason=None,
                unlock_count=UserModel.unlock_count + 1,
                updated_at=func.now(),
                version=UserModel.version + 1,
            )
            .returning(UserModel.id)
        )
        await self._session.flush()
        return tuple(result.scalars().all())

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

    async def remove_user_role(self, user_id: UUID, role_id: UUID) -> bool:
        result = await self._session.execute(
            delete(UserRoleModel)
            .where(
                UserRoleModel.user_id == user_id,
                UserRoleModel.role_id == role_id,
            )
            .returning(UserRoleModel.user_id)
        )
        await self._session.flush()
        return result.scalar_one_or_none() is not None

    async def remove_role_permission(self, role_id: UUID, permission_id: UUID) -> bool:
        result = await self._session.execute(
            delete(RolePermissionModel)
            .where(
                RolePermissionModel.role_id == role_id,
                RolePermissionModel.permission_id == permission_id,
            )
            .returning(RolePermissionModel.role_id)
        )
        await self._session.flush()
        return result.scalar_one_or_none() is not None

    async def resolve_authorization(self, user_id: UUID) -> AuthorizationSnapshot:
        role_names = frozenset(
            (
                await self._session.scalars(
                    select(RoleModel.name)
                    .join(UserRoleModel, UserRoleModel.role_id == RoleModel.id)
                    .where(UserRoleModel.user_id == user_id)
                    .distinct()
                )
            ).all()
        )
        permission_names = frozenset(
            (
                await self._session.scalars(
                    select(PermissionModel.name)
                    .join(
                        RolePermissionModel,
                        RolePermissionModel.permission_id == PermissionModel.id,
                    )
                    .join(
                        UserRoleModel,
                        UserRoleModel.role_id == RolePermissionModel.role_id,
                    )
                    .where(UserRoleModel.user_id == user_id)
                    .distinct()
                )
            ).all()
        )
        return AuthorizationSnapshot(
            roles=role_names,
            permissions=permission_names,
        )


class SqlAlchemyRefreshSessionRepository(SqlAlchemyRepository):
    async def add(self, values: RefreshSessionCreate) -> RefreshSessionRecord:
        model = RefreshSessionModel(
            **values.model_dump(
                exclude={"refresh_token_hash", "ip_address", "last_ip"},
            ),
            refresh_token_hash=values.refresh_token_hash.get_secret_value(),
            ip_address=str(values.ip_address),
            last_ip=str(values.last_ip) if values.last_ip is not None else None,
        )
        await _persist_model(self._session, model)
        return RefreshSessionRecord.model_validate(model)

    async def get_by_token_hash(
        self,
        token_hash: str,
        *,
        for_update: bool = False,
    ) -> RefreshSessionRecord | None:
        statement = select(RefreshSessionModel).where(
            RefreshSessionModel.refresh_token_hash == token_hash
        )
        if for_update:
            statement = statement.with_for_update()
        model = await self._session.scalar(statement)
        return RefreshSessionRecord.model_validate(model) if model is not None else None

    async def get_by_id(
        self,
        session_id: UUID,
    ) -> RefreshSessionRecord | None:
        model = await self._session.get(RefreshSessionModel, session_id)
        return RefreshSessionRecord.model_validate(model) if model is not None else None

    async def revoke(self, session_id: UUID) -> bool:
        result = await self._session.execute(
            update(RefreshSessionModel)
            .where(
                RefreshSessionModel.id == session_id,
                RefreshSessionModel.is_revoked.is_(False),
            )
            .values(
                is_revoked=True,
                version=RefreshSessionModel.version + 1,
            )
            .returning(RefreshSessionModel.id)
        )
        await self._session.flush()
        return result.scalar_one_or_none() is not None

    async def revoke_family(self, family_id: UUID) -> int:
        result = await self._session.execute(
            update(RefreshSessionModel)
            .where(
                RefreshSessionModel.family_id == family_id,
                RefreshSessionModel.is_revoked.is_(False),
            )
            .values(
                is_revoked=True,
                version=RefreshSessionModel.version + 1,
            )
            .returning(RefreshSessionModel.id)
        )
        await self._session.flush()
        return len(result.scalars().all())

    async def revoke_all_for_user(self, user_id: UUID) -> int:
        result = await self._session.execute(
            update(RefreshSessionModel)
            .where(
                RefreshSessionModel.user_id == user_id,
                RefreshSessionModel.is_revoked.is_(False),
            )
            .values(
                is_revoked=True,
                version=RefreshSessionModel.version + 1,
            )
            .returning(RefreshSessionModel.id)
        )
        await self._session.flush()
        return len(result.scalars().all())

    async def list_active_for_user(
        self,
        user_id: UUID,
        *,
        now: datetime,
    ) -> Sequence[RefreshSessionRecord]:
        models = (
            await self._session.scalars(
                select(RefreshSessionModel)
                .where(
                    RefreshSessionModel.user_id == user_id,
                    RefreshSessionModel.is_revoked.is_(False),
                    RefreshSessionModel.expires_at > now,
                )
                .order_by(
                    RefreshSessionModel.last_seen_at.desc(),
                    RefreshSessionModel.id.desc(),
                )
            )
        ).all()
        return tuple(RefreshSessionRecord.model_validate(model) for model in models)

    async def get_for_user(
        self,
        session_id: UUID,
        user_id: UUID,
    ) -> RefreshSessionRecord | None:
        model = await self._session.scalar(
            select(RefreshSessionModel).where(
                RefreshSessionModel.id == session_id,
                RefreshSessionModel.user_id == user_id,
            )
        )
        return RefreshSessionRecord.model_validate(model) if model is not None else None

    async def rename(
        self,
        session_id: UUID,
        user_id: UUID,
        display_name: str,
    ) -> RefreshSessionRecord | None:
        model = await self._session.scalar(
            update(RefreshSessionModel)
            .where(
                RefreshSessionModel.id == session_id,
                RefreshSessionModel.user_id == user_id,
                RefreshSessionModel.is_revoked.is_(False),
            )
            .values(
                display_name=display_name,
                version=RefreshSessionModel.version + 1,
            )
            .returning(RefreshSessionModel)
        )
        await self._session.flush()
        return RefreshSessionRecord.model_validate(model) if model is not None else None

    async def revoke_others(
        self,
        user_id: UUID,
        current_session_id: UUID,
        *,
        now: datetime,
    ) -> int:
        result = await self._session.execute(
            update(RefreshSessionModel)
            .where(
                RefreshSessionModel.user_id == user_id,
                RefreshSessionModel.id != current_session_id,
                RefreshSessionModel.is_revoked.is_(False),
                RefreshSessionModel.expires_at > now,
            )
            .values(
                is_revoked=True,
                version=RefreshSessionModel.version + 1,
            )
            .returning(RefreshSessionModel.id)
        )
        await self._session.flush()
        return len(result.scalars().all())

    async def touch_activity(
        self,
        session_id: UUID,
        *,
        observed_at: datetime,
        write_before: datetime,
        ip_address: str,
        user_agent: str,
        browser: str,
        operating_system: str,
        device_type: str,
        platform: str,
    ) -> bool:
        result = await self._session.execute(
            update(RefreshSessionModel)
            .where(
                RefreshSessionModel.id == session_id,
                RefreshSessionModel.is_revoked.is_(False),
                RefreshSessionModel.expires_at > observed_at,
                RefreshSessionModel.last_seen_at <= write_before,
            )
            .values(
                last_seen_at=observed_at,
                last_activity_at=observed_at,
                last_ip=ip_address,
                last_user_agent=user_agent,
                last_browser=browser,
                last_operating_system=operating_system,
                last_device_type=device_type,
                platform=platform,
                version=RefreshSessionModel.version + 1,
            )
            .returning(RefreshSessionModel.id)
        )
        await self._session.flush()
        return result.scalar_one_or_none() is not None

    async def count_by_state(self, *, now: datetime) -> tuple[int, int]:
        active = await self._session.scalar(
            select(func.count())
            .select_from(RefreshSessionModel)
            .where(
                RefreshSessionModel.is_revoked.is_(False),
                RefreshSessionModel.expires_at > now,
            )
        )
        revoked = await self._session.scalar(
            select(func.count())
            .select_from(RefreshSessionModel)
            .where(RefreshSessionModel.is_revoked.is_(True))
        )
        return int(active or 0), int(revoked or 0)

    async def revoke_expired(self, *, now: datetime) -> int:
        result = await self._session.execute(
            update(RefreshSessionModel)
            .where(
                RefreshSessionModel.is_revoked.is_(False),
                RefreshSessionModel.expires_at <= now,
            )
            .values(
                is_revoked=True,
                version=RefreshSessionModel.version + 1,
            )
            .returning(RefreshSessionModel.id)
        )
        await self._session.flush()
        return len(result.scalars().all())

    async def delete_expired_revoked(
        self,
        *,
        expired_before: datetime,
        limit: int,
    ) -> int:
        child = aliased(RefreshSessionModel)
        candidate_ids = (
            select(RefreshSessionModel.id)
            .where(
                RefreshSessionModel.is_revoked.is_(True),
                RefreshSessionModel.expires_at <= expired_before,
                ~select(child.id)
                .where(child.parent_session_id == RefreshSessionModel.id)
                .exists(),
            )
            .order_by(
                RefreshSessionModel.expires_at,
                RefreshSessionModel.id,
            )
            .limit(limit)
        )
        result = await self._session.execute(
            delete(RefreshSessionModel)
            .where(RefreshSessionModel.id.in_(candidate_ids))
            .returning(RefreshSessionModel.id)
        )
        await self._session.flush()
        return len(result.scalars().all())


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

    async def count_recent_failures(self, email: str, *, since: datetime) -> int:
        normalized_email = normalize_email(email)
        last_success = await self._session.scalar(
            select(func.max(LoginAttemptModel.occurred_at)).where(
                LoginAttemptModel.email == normalized_email,
                LoginAttemptModel.success.is_(True),
                LoginAttemptModel.occurred_at >= since,
            )
        )
        failure_boundary = max(since, last_success) if last_success else since
        count = await self._session.scalar(
            select(func.count())
            .select_from(LoginAttemptModel)
            .where(
                LoginAttemptModel.email == normalized_email,
                LoginAttemptModel.success.is_(False),
                LoginAttemptModel.occurred_at > failure_boundary,
            )
        )
        return int(count or 0)


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

    async def consume(self, token_hash: str, *, now: datetime) -> bool:
        return await _consume_token(
            self._session,
            EmailVerificationTokenModel,
            token_hash,
            now,
        )

    async def invalidate_for_user(self, user_id: UUID) -> int:
        return await _invalidate_tokens(
            self._session,
            EmailVerificationTokenModel,
            user_id,
        )

    async def delete_expired(self, *, now: datetime, limit: int) -> int:
        return await _delete_expired_tokens(
            self._session,
            EmailVerificationTokenModel,
            now,
            limit,
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

    async def consume(self, token_hash: str, *, now: datetime) -> bool:
        return await _consume_token(
            self._session,
            PasswordResetTokenModel,
            token_hash,
            now,
        )

    async def invalidate_for_user(self, user_id: UUID) -> int:
        return await _invalidate_tokens(
            self._session,
            PasswordResetTokenModel,
            user_id,
        )

    async def delete_expired(self, *, now: datetime, limit: int) -> int:
        return await _delete_expired_tokens(
            self._session,
            PasswordResetTokenModel,
            now,
            limit,
        )


async def _consume_token(
    session: AsyncSession,
    model: type[EmailVerificationTokenModel] | type[PasswordResetTokenModel],
    token_hash: str,
    now: datetime,
) -> bool:
    result = await session.execute(
        update(model)
        .where(
            model.token_hash == token_hash,
            model.is_used.is_(False),
            model.expires_at > now,
        )
        .values(is_used=True)
        .returning(model.id)
    )
    await session.flush()
    return result.scalar_one_or_none() is not None


async def _invalidate_tokens(
    session: AsyncSession,
    model: type[EmailVerificationTokenModel] | type[PasswordResetTokenModel],
    user_id: UUID,
) -> int:
    result = await session.execute(
        update(model)
        .where(model.user_id == user_id, model.is_used.is_(False))
        .values(is_used=True)
        .returning(model.id)
    )
    await session.flush()
    return len(result.scalars().all())


async def _delete_expired_tokens(
    session: AsyncSession,
    model: type[EmailVerificationTokenModel] | type[PasswordResetTokenModel],
    now: datetime,
    limit: int,
) -> int:
    candidate_ids = (
        select(model.id)
        .where(model.expires_at <= now)
        .order_by(model.expires_at, model.id)
        .limit(limit)
    )
    result = await session.execute(
        delete(model).where(model.id.in_(candidate_ids)).returning(model.id)
    )
    await session.flush()
    return len(result.scalars().all())
