from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status

from app.common.context import get_request_context
from app.modules.identity.api.dependencies import (
    AuthenticationServiceDependency,
    CurrentIdentity,
)
from app.modules.identity.api.schemas import (
    AuthenticationRequest,
    LogoutAllResponse,
    RefreshRequest,
    TokenResponse,
)
from app.modules.identity.application.services import (
    AuthenticationTokens,
    authentication_context,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _token_response(tokens: AuthenticationTokens) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token.get_secret_value(),
        expires_in=tokens.expires_in,
        token_type=tokens.token_type,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate an identity",
    responses={
        401: {
            "description": "Invalid credentials or ineligible account",
            "content": {
                "application/problem+json": {
                    "example": {
                        "title": "Authentication failed",
                        "status": 401,
                        "detail": "Invalid email or password.",
                        "code": "unauthorized",
                    }
                }
            },
        }
    },
)
async def login(
    payload: AuthenticationRequest,
    service: AuthenticationServiceDependency,
    request: Request,
    user_agent: Annotated[str | None, Header()] = None,
) -> TokenResponse:
    context = get_request_context()
    tokens = await service.login(
        email=payload.email,
        password=payload.password,
        context=authentication_context(
            client_ip=context.client_ip,
            user_agent=user_agent,
            device_name=payload.device_name,
        ),
    )
    return _token_response(tokens)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate an opaque refresh token",
)
async def refresh(
    payload: RefreshRequest,
    service: AuthenticationServiceDependency,
) -> TokenResponse:
    return _token_response(await service.refresh(payload.refresh_token))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current session",
)
async def logout(
    identity: CurrentIdentity,
    service: AuthenticationServiceDependency,
) -> Response:
    await service.logout(identity.session.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/logout-all",
    response_model=LogoutAllResponse,
    summary="Revoke every active session for the current identity",
)
async def logout_all(
    identity: CurrentIdentity,
    service: AuthenticationServiceDependency,
) -> LogoutAllResponse:
    count = await service.logout_all(identity.user.id)
    return LogoutAllResponse(revoked_sessions=count)
