from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response, status

from app.modules.identity.api.dependencies import (
    CurrentIdentity,
    SessionManagementServiceDependency,
)
from app.modules.identity.api.session_schemas import (
    RenameSessionRequest,
    RevokeOthersResponse,
    SessionListResponse,
    SessionResponse,
)
from app.modules.identity.application.schemas import RefreshSessionRecord

router = APIRouter(prefix="/sessions", tags=["Sessions"])

_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        "description": "Missing, invalid, expired, or revoked access token",
        "content": {
            "application/problem+json": {
                "example": {
                    "title": "Authentication failed",
                    "status": 401,
                    "detail": "Authentication credentials are invalid.",
                    "code": "unauthorized",
                }
            }
        },
    }
}
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_AUTH_RESPONSES,
    404: {
        "description": "Session not found or not owned by the identity",
        "content": {
            "application/problem+json": {
                "example": {
                    "title": "Session not found",
                    "status": 404,
                    "detail": "The requested session was not found.",
                    "code": "not_found",
                }
            }
        },
    },
    409: {
        "description": "Session is already revoked or no longer active",
        "content": {
            "application/problem+json": {
                "example": {
                    "title": "Session conflict",
                    "status": 409,
                    "detail": "The session is already revoked.",
                    "code": "conflict",
                }
            }
        },
    },
}


def _response(
    record: RefreshSessionRecord, *, current_session_id: UUID
) -> SessionResponse:
    return SessionResponse(
        id=record.id,
        display_name=record.display_name,
        browser=record.last_browser or record.browser,
        operating_system=record.last_operating_system or record.operating_system,
        device_type=record.last_device_type,
        platform=record.platform,
        last_ip=str(record.last_ip or record.ip_address),
        last_seen_at=record.last_seen_at,
        created_at=record.created_at,
        expires_at=record.expires_at,
        country=record.last_country,
        city=record.city,
        is_trusted=record.is_trusted,
        risk_score=record.risk_score,
        session_version=record.version,
        current=record.id == current_session_id,
        can_rename=True,
        can_revoke=record.id != current_session_id,
    )


@router.get(
    "",
    response_model=SessionListResponse,
    summary="List active sessions",
    description="Returns only active, unexpired sessions owned by this identity.",
    responses=_AUTH_RESPONSES,
)
async def list_sessions(
    identity: CurrentIdentity,
    service: SessionManagementServiceDependency,
) -> SessionListResponse:
    records = await service.list_active(identity.user.id)
    return SessionListResponse(
        sessions=[
            _response(record, current_session_id=identity.session.id)
            for record in records
        ]
    )


@router.get(
    "/current",
    response_model=SessionResponse,
    summary="Get the current session",
    responses=_ERROR_RESPONSES,
)
async def current_session(
    identity: CurrentIdentity,
    service: SessionManagementServiceDependency,
) -> SessionResponse:
    record = await service.current(identity.user.id, identity.session.id)
    return _response(record, current_session_id=identity.session.id)


@router.patch(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Rename an active session",
    responses=_ERROR_RESPONSES,
)
async def rename_session(
    session_id: UUID,
    payload: RenameSessionRequest,
    identity: CurrentIdentity,
    service: SessionManagementServiceDependency,
) -> SessionResponse:
    record = await service.rename(identity.user.id, session_id, payload.display_name)
    return _response(record, current_session_id=identity.session.id)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an active session",
    responses=_ERROR_RESPONSES,
)
async def revoke_session(
    session_id: UUID,
    identity: CurrentIdentity,
    service: SessionManagementServiceDependency,
) -> Response:
    await service.revoke(
        identity.user.id,
        session_id,
        current_session_id=identity.session.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/revoke-others",
    response_model=RevokeOthersResponse,
    summary="Revoke every other active session",
    description="Preserves the access-token session used for this request.",
    responses=_AUTH_RESPONSES,
)
async def revoke_other_sessions(
    identity: CurrentIdentity,
    service: SessionManagementServiceDependency,
) -> RevokeOthersResponse:
    count = await service.revoke_others(identity.user.id, identity.session.id)
    return RevokeOthersResponse(revoked_sessions=count)
