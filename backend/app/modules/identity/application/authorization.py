from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.context import maybe_get_request_context
from app.common.errors import ErrorCode
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.identity.application.repositories import (
    IdentityGrantRepository,
    PermissionRepository,
    RoleRepository,
)
from app.modules.identity.application.schemas import (
    PermissionCreate,
    RolePermissionCreate,
    UserRoleCreate,
)
from app.modules.identity.domain.authorization import (
    AuthorizationPrincipal,
    AuthorizationSnapshot,
    PermissionRegistry,
)
from app.modules.identity.domain.authorization_events import (
    AuthorizationDenied,
    AuthorizationGranted,
    PermissionCacheHit,
    PermissionCacheMiss,
    PermissionGranted,
    PermissionRevoked,
    RoleAssigned,
    RoleRevoked,
)
from app.observability.metrics import (
    AUTHORIZATION_CHECKS,
    AUTHORIZATION_DENIED,
    PERMISSION_CACHE_HITS,
    PERMISSION_CACHE_MISSES,
)


class PermissionCache(Protocol):
    async def get(self, user_id: UUID) -> AuthorizationSnapshot | None: ...

    async def set(self, user_id: UUID, snapshot: AuthorizationSnapshot) -> None: ...

    async def invalidate_user(self, user_id: UUID) -> None: ...

    async def invalidate_all(self) -> None: ...

    async def close(self) -> None: ...


class PermissionResolver:
    """Resolve effective RBAC state from cache or authoritative PostgreSQL."""

    def __init__(
        self,
        grants: IdentityGrantRepository,
        cache: PermissionCache,
        events: EventPublisher,
    ) -> None:
        self._grants = grants
        self._cache = cache
        self._events = events

    async def resolve(self, user_id: UUID) -> AuthorizationSnapshot:
        cached = await self._cache.get(user_id)
        if cached is not None:
            PERMISSION_CACHE_HITS.inc()
            await self._events.publish(
                PermissionCacheHit(correlation_id=_correlation_id())
            )
            return cached

        PERMISSION_CACHE_MISSES.inc()
        await self._events.publish(
            PermissionCacheMiss(correlation_id=_correlation_id())
        )
        snapshot = await self._grants.resolve_authorization(user_id)
        await self._cache.set(user_id, snapshot)
        return snapshot


class AuthorizationService:
    """Authoritative role and permission decisions with deny-by-default errors."""

    def __init__(
        self,
        resolver: PermissionResolver,
        registry: PermissionRegistry,
        events: EventPublisher,
    ) -> None:
        self._resolver = resolver
        self._registry = registry
        self._events = events

    async def has_permission(
        self,
        identity: AuthorizationPrincipal,
        permission: str,
    ) -> bool:
        required = self._registry.parse(permission).name
        snapshot = await self._resolver.resolve(identity.user_id)
        return await self._record_decision(
            identity,
            required in snapshot.permissions,
            required,
        )

    async def require_permission(
        self,
        identity: AuthorizationPrincipal,
        permission: str,
    ) -> None:
        if not await self.has_permission(identity, permission):
            raise _forbidden()

    async def require_any_permission(
        self,
        identity: AuthorizationPrincipal,
        permissions: set[str] | frozenset[str],
    ) -> None:
        required = self._validated_permissions(permissions)
        snapshot = await self._resolver.resolve(identity.user_id)
        granted = bool(required.intersection(snapshot.permissions))
        if not await self._record_decision(
            identity,
            granted,
            f"any({','.join(sorted(required))})",
        ):
            raise _forbidden()

    async def require_all_permissions(
        self,
        identity: AuthorizationPrincipal,
        permissions: set[str] | frozenset[str],
    ) -> None:
        required = self._validated_permissions(permissions)
        snapshot = await self._resolver.resolve(identity.user_id)
        granted = required.issubset(snapshot.permissions)
        if not await self._record_decision(
            identity,
            granted,
            f"all({','.join(sorted(required))})",
        ):
            raise _forbidden()

    async def require_role(
        self,
        identity: AuthorizationPrincipal,
        role: str,
    ) -> None:
        required = self._registry.validate_role(role)
        snapshot = await self._resolver.resolve(identity.user_id)
        if not await self._record_decision(
            identity,
            required in snapshot.roles,
            f"role:{required}",
        ):
            raise _forbidden()

    def _validated_permissions(
        self,
        permissions: set[str] | frozenset[str],
    ) -> frozenset[str]:
        if not permissions:
            raise ValueError("at least one permission is required")
        return frozenset(
            self._registry.parse(permission).name for permission in permissions
        )

    async def _record_decision(
        self,
        identity: AuthorizationPrincipal,
        granted: bool,
        requirement: str,
    ) -> bool:
        AUTHORIZATION_CHECKS.inc()
        event_type = AuthorizationGranted if granted else AuthorizationDenied
        if not granted:
            AUTHORIZATION_DENIED.inc()
        await self._events.publish(
            event_type(
                user_id=identity.user_id,
                requirement=requirement,
                correlation_id=_correlation_id(),
            )
        )
        return granted


class PermissionService:
    """Manage database-driven RBAC grants and their cache invalidation."""

    def __init__(
        self,
        db_session: AsyncSession,
        roles: RoleRepository,
        permissions: PermissionRepository,
        grants: IdentityGrantRepository,
        cache: PermissionCache,
        registry: PermissionRegistry,
        events: EventPublisher,
    ) -> None:
        self._db_session = db_session
        self._roles = roles
        self._permissions = permissions
        self._grants = grants
        self._cache = cache
        self._registry = registry
        self._events = events

    async def register_permission(
        self,
        name: str,
        *,
        description: str | None = None,
    ) -> None:
        parsed = self._registry.parse(name)
        async with _transaction(self._db_session):
            await self._permissions.add(
                PermissionCreate(
                    name=parsed.name,
                    description=description,
                    resource=parsed.resource,
                    action=parsed.action,
                )
            )
        await self._cache.invalidate_all()

    async def assign_role(
        self,
        user_id: UUID,
        role_name: str,
        *,
        assigned_by_id: UUID | None = None,
    ) -> None:
        role = await self._roles.get_by_name(self._registry.validate_role(role_name))
        if role is None:
            raise _not_found("Role")
        async with _transaction(self._db_session):
            await self._grants.add_user_role(
                UserRoleCreate(
                    user_id=user_id,
                    role_id=role.id,
                    assigned_by_id=assigned_by_id,
                )
            )
        await self._cache.invalidate_user(user_id)
        await self._events.publish(
            RoleAssigned(
                user_id=user_id,
                role_name=role.name,
                actor_user_id=assigned_by_id,
                correlation_id=_correlation_id(),
            )
        )

    async def revoke_role(
        self,
        user_id: UUID,
        role_name: str,
        *,
        revoked_by_id: UUID | None = None,
    ) -> bool:
        role = await self._roles.get_by_name(self._registry.validate_role(role_name))
        if role is None:
            raise _not_found("Role")
        async with _transaction(self._db_session):
            removed = await self._grants.remove_user_role(user_id, role.id)
        await self._cache.invalidate_user(user_id)
        if removed:
            await self._events.publish(
                RoleRevoked(
                    user_id=user_id,
                    role_name=role.name,
                    actor_user_id=revoked_by_id,
                    correlation_id=_correlation_id(),
                )
            )
        return removed

    async def assign_permission(
        self,
        role_name: str,
        permission_name: str,
        *,
        assigned_by_id: UUID | None = None,
    ) -> None:
        role = await self._roles.get_by_name(self._registry.validate_role(role_name))
        permission = await self._permissions.get_by_name(
            self._registry.parse(permission_name).name
        )
        if role is None:
            raise _not_found("Role")
        if permission is None:
            raise _not_found("Permission")
        async with _transaction(self._db_session):
            await self._grants.add_role_permission(
                RolePermissionCreate(
                    role_id=role.id,
                    permission_id=permission.id,
                    assigned_by_id=assigned_by_id,
                )
            )
        await self._cache.invalidate_all()
        await self._events.publish(
            PermissionGranted(
                role_name=role.name,
                permission_name=permission.name,
                actor_user_id=assigned_by_id,
                correlation_id=_correlation_id(),
            )
        )

    async def revoke_permission(
        self,
        role_name: str,
        permission_name: str,
        *,
        revoked_by_id: UUID | None = None,
    ) -> bool:
        role = await self._roles.get_by_name(self._registry.validate_role(role_name))
        permission = await self._permissions.get_by_name(
            self._registry.parse(permission_name).name
        )
        if role is None:
            raise _not_found("Role")
        if permission is None:
            raise _not_found("Permission")
        async with _transaction(self._db_session):
            removed = await self._grants.remove_role_permission(
                role.id,
                permission.id,
            )
        await self._cache.invalidate_all()
        if removed:
            await self._events.publish(
                PermissionRevoked(
                    role_name=role.name,
                    permission_name=permission.name,
                    actor_user_id=revoked_by_id,
                    correlation_id=_correlation_id(),
                )
            )
        return removed


def _forbidden() -> AppError:
    return AppError(
        code=ErrorCode.FORBIDDEN,
        title="Access denied",
        detail="You do not have permission to perform this action.",
        status_code=403,
    )


def _not_found(resource: str) -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title=f"{resource} not found",
        detail=f"The requested {resource.lower()} was not found.",
        status_code=404,
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
