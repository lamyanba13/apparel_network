from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

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
from app.modules.identity.domain.authorization import AuthorizationSnapshot


class UserRepository(Protocol):
    async def add(self, values: UserCreate) -> UserRecord: ...

    async def get_by_id(
        self,
        user_id: UUID,
        *,
        include_deleted: bool = False,
        for_update: bool = False,
    ) -> UserRecord | None: ...

    async def get_by_email(
        self,
        email: str,
        *,
        include_deleted: bool = False,
        for_update: bool = False,
    ) -> UserRecord | None: ...

    async def update_password(self, user_id: UUID, password_hash: str) -> bool: ...

    async def mark_email_verified(self, user_id: UUID, *, at: datetime) -> bool: ...

    async def set_lock(
        self,
        user_id: UUID,
        *,
        locked_until: datetime,
        reason: str,
    ) -> bool: ...

    async def unlock(self, user_id: UUID) -> bool: ...

    async def unlock_expired(self, *, now: datetime, limit: int) -> Sequence[UUID]: ...


class RoleRepository(Protocol):
    async def add(self, values: RoleCreate) -> RoleRecord: ...

    async def get_by_name(self, name: str) -> RoleRecord | None: ...


class PermissionRepository(Protocol):
    async def add(self, values: PermissionCreate) -> PermissionRecord: ...

    async def get_by_name(self, name: str) -> PermissionRecord | None: ...


class IdentityGrantRepository(Protocol):
    async def add_user_role(self, values: UserRoleCreate) -> UserRoleRecord: ...

    async def add_role_permission(
        self,
        values: RolePermissionCreate,
    ) -> RolePermissionRecord: ...

    async def remove_user_role(self, user_id: UUID, role_id: UUID) -> bool: ...

    async def remove_role_permission(
        self, role_id: UUID, permission_id: UUID
    ) -> bool: ...

    async def resolve_authorization(self, user_id: UUID) -> AuthorizationSnapshot: ...


class RefreshSessionRepository(Protocol):
    async def add(self, values: RefreshSessionCreate) -> RefreshSessionRecord: ...

    async def get_by_token_hash(
        self,
        token_hash: str,
        *,
        for_update: bool = False,
    ) -> RefreshSessionRecord | None: ...

    async def get_by_id(
        self,
        session_id: UUID,
    ) -> RefreshSessionRecord | None: ...

    async def revoke(self, session_id: UUID) -> bool: ...

    async def revoke_family(self, family_id: UUID) -> int: ...

    async def revoke_all_for_user(self, user_id: UUID) -> int: ...

    async def list_active_for_user(
        self, user_id: UUID, *, now: datetime
    ) -> Sequence[RefreshSessionRecord]: ...

    async def get_for_user(
        self, session_id: UUID, user_id: UUID
    ) -> RefreshSessionRecord | None: ...

    async def rename(
        self, session_id: UUID, user_id: UUID, display_name: str
    ) -> RefreshSessionRecord | None: ...

    async def revoke_others(
        self, user_id: UUID, current_session_id: UUID, *, now: datetime
    ) -> int: ...

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
    ) -> bool: ...

    async def count_by_state(self, *, now: datetime) -> tuple[int, int]: ...

    async def revoke_expired(self, *, now: datetime) -> int: ...

    async def delete_expired_revoked(
        self, *, expired_before: datetime, limit: int
    ) -> int: ...


class PasswordHistoryRepository(Protocol):
    async def add(
        self,
        values: PasswordHistoryCreate,
    ) -> PasswordHistoryRecord: ...

    async def list_recent(
        self,
        user_id: UUID,
        *,
        limit: int,
    ) -> Sequence[PasswordHistoryRecord]: ...


class LoginAttemptRepository(Protocol):
    async def add(self, values: LoginAttemptCreate) -> LoginAttemptRecord: ...

    async def count_recent_failures(self, email: str, *, since: datetime) -> int: ...


class EmailVerificationTokenRepository(Protocol):
    async def add(
        self,
        values: EmailVerificationTokenCreate,
    ) -> EmailVerificationTokenRecord: ...

    async def get_by_hash(
        self,
        token_hash: str,
    ) -> EmailVerificationTokenRecord | None: ...

    async def consume(self, token_hash: str, *, now: datetime) -> bool: ...

    async def invalidate_for_user(self, user_id: UUID) -> int: ...

    async def delete_expired(self, *, now: datetime, limit: int) -> int: ...


class PasswordResetTokenRepository(Protocol):
    async def add(
        self,
        values: PasswordResetTokenCreate,
    ) -> PasswordResetTokenRecord: ...

    async def get_by_hash(
        self,
        token_hash: str,
    ) -> PasswordResetTokenRecord | None: ...

    async def consume(self, token_hash: str, *, now: datetime) -> bool: ...

    async def invalidate_for_user(self, user_id: UUID) -> int: ...

    async def delete_expired(self, *, now: datetime, limit: int) -> int: ...
