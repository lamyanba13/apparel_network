from __future__ import annotations

from collections.abc import Sequence
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


class UserRepository(Protocol):
    async def add(self, values: UserCreate) -> UserRecord: ...

    async def get_by_id(
        self,
        user_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> UserRecord | None: ...

    async def get_by_email(
        self,
        email: str,
        *,
        include_deleted: bool = False,
    ) -> UserRecord | None: ...


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


class RefreshSessionRepository(Protocol):
    async def add(self, values: RefreshSessionCreate) -> RefreshSessionRecord: ...

    async def get_by_token_hash(
        self,
        token_hash: str,
    ) -> RefreshSessionRecord | None: ...


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


class EmailVerificationTokenRepository(Protocol):
    async def add(
        self,
        values: EmailVerificationTokenCreate,
    ) -> EmailVerificationTokenRecord: ...

    async def get_by_hash(
        self,
        token_hash: str,
    ) -> EmailVerificationTokenRecord | None: ...


class PasswordResetTokenRepository(Protocol):
    async def add(
        self,
        values: PasswordResetTokenCreate,
    ) -> PasswordResetTokenRecord: ...

    async def get_by_hash(
        self,
        token_hash: str,
    ) -> PasswordResetTokenRecord | None: ...
