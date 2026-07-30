from fastapi import APIRouter, Response, status

from app.modules.identity.api.account_schemas import (
    EmailResendRequest,
    EmailVerifyRequest,
    GenericAcceptedResponse,
    PasswordChangeRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
)
from app.modules.identity.api.dependencies import (
    AccountSecurityServiceDependency,
    CurrentIdentity,
)

router = APIRouter(prefix="/account", tags=["Account Security"])

_GENERIC_RECOVERY_MESSAGE = (
    "If the account is eligible, further instructions will be sent."
)


@router.post(
    "/password/change",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the current identity password",
    description=(
        "Requires the current password, enforces the configured password "
        "policy and history, and revokes every other active session."
    ),
    responses={
        401: {"description": "Authentication or current password rejected"},
        422: {"description": "The new password violates policy"},
    },
)
async def change_password(
    payload: PasswordChangeRequest,
    identity: CurrentIdentity,
    service: AccountSecurityServiceDependency,
) -> Response:
    await service.change_password(
        user_id=identity.user.id,
        current_session_id=identity.session.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/password/forgot",
    response_model=GenericAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request password recovery",
    description=(
        "Always returns the same response so account existence and eligibility "
        "cannot be inferred."
    ),
)
async def forgot_password(
    payload: PasswordForgotRequest,
    service: AccountSecurityServiceDependency,
) -> GenericAcceptedResponse:
    await service.request_password_reset(payload.email)
    return GenericAcceptedResponse(message=_GENERIC_RECOVERY_MESSAGE)


@router.post(
    "/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset a password with a single-use opaque token",
    responses={
        400: {"description": "Token is invalid, expired, or already used"},
        422: {"description": "The new password violates policy"},
    },
)
async def reset_password(
    payload: PasswordResetRequest,
    service: AccountSecurityServiceDependency,
) -> Response:
    await service.reset_password(
        token=payload.token,
        new_password=payload.new_password,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/email/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Verify an email with a single-use opaque token",
    description=(
        "The operation is idempotent and returns the same response for invalid, "
        "expired, used, and already-completed verification attempts."
    ),
)
async def verify_email(
    payload: EmailVerifyRequest,
    service: AccountSecurityServiceDependency,
) -> Response:
    await service.verify_email(payload.token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/email/resend",
    response_model=GenericAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request another email-verification message",
    description=(
        "Always returns the same response so account existence and verification "
        "state cannot be inferred."
    ),
)
async def resend_email_verification(
    payload: EmailResendRequest,
    service: AccountSecurityServiceDependency,
) -> GenericAcceptedResponse:
    await service.request_email_verification(payload.email)
    return GenericAcceptedResponse(message=_GENERIC_RECOVERY_MESSAGE)
