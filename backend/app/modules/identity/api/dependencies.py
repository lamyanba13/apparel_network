from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import Settings
from app.common.errors import ErrorCode
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.database.session import get_db
from app.modules.identity.application.schemas import RefreshSessionRecord
from app.modules.identity.application.services import (
    AuthenticatedIdentity,
    AuthenticationService,
    PasswordService,
    SessionService,
    TokenService,
)
from app.modules.identity.application.session_management import (
    SessionManagementService,
)
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyLoginAttemptRepository,
    SqlAlchemyRefreshSessionRepository,
    SqlAlchemyUserRepository,
)

_bearer = HTTPBearer(
    auto_error=False,
    bearerFormat="JWT",
    description="Short-lived Fashion Network access token.",
)


def authentication_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AuthenticationService:
    settings = cast(Settings, request.app.state.settings)
    password_service = cast(PasswordService, request.app.state.password_service)
    token_service = cast(TokenService | None, request.app.state.token_service)
    event_publisher = cast(EventPublisher, request.app.state.authentication_events)
    if token_service is None:
        raise AppError(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            title="Authentication unavailable",
            detail="Authentication is not configured.",
            status_code=503,
        )
    session_repository = SqlAlchemyRefreshSessionRepository(session)
    return AuthenticationService(
        session,
        SqlAlchemyUserRepository(session),
        SqlAlchemyLoginAttemptRepository(session),
        SessionService(
            session_repository,
            token_service,
            event_publisher,
            refresh_lifetime=timedelta(days=settings.auth_refresh_token_lifetime_days),
        ),
        session_repository,
        password_service,
        token_service,
        event_publisher,
        require_verified_email=settings.auth_require_verified_email,
    )


async def optional_identity_dependency(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
    service: Annotated[
        AuthenticationService, Depends(authentication_service_dependency)
    ],
) -> AuthenticatedIdentity | None:
    if credentials is None:
        return None
    return await service.authenticate_access_token(credentials.credentials)


async def current_identity_dependency(
    request: Request,
    identity: Annotated[
        AuthenticatedIdentity | None,
        Depends(optional_identity_dependency),
    ],
) -> AuthenticatedIdentity:
    if identity is None:
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            title="Authentication required",
            detail="Authentication credentials are required.",
            status_code=401,
        )
    request.state.authenticated_session_id = identity.session.id
    return identity


async def session_management_service_dependency(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[SessionManagementService]:
    events = cast(EventPublisher, request.app.state.authentication_events)
    try:
        yield SessionManagementService(
            session,
            SqlAlchemyRefreshSessionRepository(session),
            events,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def authenticated_session_dependency(
    identity: Annotated[
        AuthenticatedIdentity,
        Depends(current_identity_dependency),
    ],
) -> RefreshSessionRecord:
    return identity.session


AuthenticationServiceDependency = Annotated[
    AuthenticationService,
    Depends(authentication_service_dependency),
]
CurrentIdentity = Annotated[
    AuthenticatedIdentity,
    Depends(current_identity_dependency),
]
OptionalIdentity = Annotated[
    AuthenticatedIdentity | None,
    Depends(optional_identity_dependency),
]
SessionManagementServiceDependency = Annotated[
    SessionManagementService,
    Depends(session_management_service_dependency),
]
