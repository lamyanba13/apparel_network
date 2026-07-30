from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.identity.application.authorization import (
    AuthorizationService,
    PermissionCache,
    PermissionResolver,
)
from app.modules.identity.domain.authorization import (
    AuthorizationPrincipal,
    PermissionRegistry,
)
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyIdentityGrantRepository,
)


@dataclass(frozen=True, slots=True)
class AuthorizationRequirement:
    kind: str
    values: tuple[str, ...]


def authorization_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AuthorizationService:
    events = cast(EventPublisher, request.app.state.authentication_events)
    cache = cast(PermissionCache, request.app.state.permission_cache)
    return AuthorizationService(
        PermissionResolver(
            SqlAlchemyIdentityGrantRepository(session),
            cache,
            events,
        ),
        PermissionRegistry(),
        events,
    )


AuthorizationServiceDependency = Annotated[
    AuthorizationService,
    Depends(authorization_service_dependency),
]


def require_permission(permission: str) -> Any:
    canonical = PermissionRegistry().parse(permission).name

    async def check(
        identity: CurrentIdentity,
        service: AuthorizationServiceDependency,
    ) -> None:
        await service.require_permission(_principal(identity), canonical)

    _mark(check, "permission", (canonical,))
    return Depends(check)


def require_role(role: str) -> Any:
    canonical = PermissionRegistry().validate_role(role)

    async def check(
        identity: CurrentIdentity,
        service: AuthorizationServiceDependency,
    ) -> None:
        await service.require_role(_principal(identity), canonical)

    _mark(check, "role", (canonical,))
    return Depends(check)


def require_any_permission(*permissions: str) -> Any:
    canonical = _permissions(permissions)

    async def check(
        identity: CurrentIdentity,
        service: AuthorizationServiceDependency,
    ) -> None:
        await service.require_any_permission(_principal(identity), set(canonical))

    _mark(check, "any_permission", canonical)
    return Depends(check)


def require_all_permissions(*permissions: str) -> Any:
    canonical = _permissions(permissions)

    async def check(
        identity: CurrentIdentity,
        service: AuthorizationServiceDependency,
    ) -> None:
        await service.require_all_permissions(_principal(identity), set(canonical))

    _mark(check, "all_permissions", canonical)
    return Depends(check)


def _permissions(values: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        raise ValueError("at least one permission is required")
    registry = PermissionRegistry()
    return tuple(registry.parse(value).name for value in values)


def _principal(identity: Any) -> AuthorizationPrincipal:
    return AuthorizationPrincipal(
        user_id=identity.user.id,
        session_id=identity.session.id,
    )


def _mark(
    dependency: Callable[..., Any],
    kind: str,
    values: tuple[str, ...],
) -> None:
    dependency.__dict__["__authorization_requirement__"] = AuthorizationRequirement(
        kind=kind,
        values=values,
    )
