from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.common.pagination import OffsetPagination, PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.stores.api.dependencies import StoreMembershipServiceDependency
from app.modules.stores.api.membership_schemas import (
    StoreMembershipInviteRequest,
    StoreMembershipListResponse,
    StoreMembershipResponse,
    StoreMembershipUpdateRequest,
    StoreMembershipVersionRequest,
)
from app.modules.stores.application.membership_schemas import (
    StoreMembershipInvitation,
    StoreMembershipUpdate,
)
from app.modules.stores.domain import StoreMembership

router = APIRouter(
    prefix="/stores/{store_id}/members",
    tags=["Store Memberships"],
)

_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Store permission"},
}
_RESOURCE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_AUTH_RESPONSES,
    404: {"description": "Store, user, or membership not found"},
}
_MUTATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_RESOURCE_RESPONSES,
    409: {
        "description": (
            "Duplicate membership, invalid lifecycle transition, or stale version"
        )
    },
    422: {"description": "Membership request validation failed"},
}


def _response(value: StoreMembership) -> StoreMembershipResponse:
    return StoreMembershipResponse(
        id=value.id,
        store_id=value.store_id,
        user_id=value.user_id,
        role=value.role,
        status=value.status,
        invited_by_id=value.invited_by_id,
        invitation_expires_at=value.invitation_expires_at,
        accepted_at=value.accepted_at,
        removed_at=value.removed_at,
        version=value.version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


@router.post(
    "",
    response_model=StoreMembershipResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a Store member",
    description=(
        "Creates a seven-day staff or manager invitation for an existing user. "
        "Owner invitations and duplicate live memberships are rejected."
    ),
    dependencies=[require_permission("store:update")],
    responses=_MUTATION_RESPONSES,
)
async def invite_store_member(
    store_id: UUID,
    payload: StoreMembershipInviteRequest,
    identity: CurrentIdentity,
    service: StoreMembershipServiceDependency,
    response: Response,
) -> StoreMembershipResponse:
    membership = await service.invite(
        store_id,
        identity.user.id,
        StoreMembershipInvitation(user_id=payload.user_id, role=payload.role),
    )
    response.headers["Location"] = f"/api/v1/stores/{store_id}/members/{membership.id}"
    return _response(membership)


@router.get(
    "",
    response_model=StoreMembershipListResponse,
    summary="List Store memberships",
    description=(
        "Returns a bounded owner-scoped membership and invitation history. "
        "Expired pending invitations are finalized before the read."
    ),
    dependencies=[require_permission("store:view")],
    responses=_RESOURCE_RESPONSES,
)
async def list_store_members(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreMembershipServiceDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> StoreMembershipListResponse:
    pagination = OffsetPagination(offset=offset, limit=limit)
    members, total = await service.list(
        store_id,
        identity.user.id,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return StoreMembershipListResponse(
        items=[_response(member) for member in members],
        page=PageMetadata(
            has_more=pagination.offset + len(members) < total,
            limit=pagination.limit,
            total=total,
            offset=pagination.offset,
        ),
    )


@router.patch(
    "/{member_id}",
    response_model=StoreMembershipResponse,
    summary="Update a Store membership",
    description=(
        "Changes a non-owner membership role, suspends an active membership, "
        "or reactivates a suspended membership using optimistic concurrency."
    ),
    dependencies=[require_permission("store:update")],
    responses=_MUTATION_RESPONSES,
)
async def update_store_member(
    store_id: UUID,
    member_id: UUID,
    payload: StoreMembershipUpdateRequest,
    identity: CurrentIdentity,
    service: StoreMembershipServiceDependency,
) -> StoreMembershipResponse:
    return _response(
        await service.update(
            store_id,
            member_id,
            identity.user.id,
            StoreMembershipUpdate(
                expected_version=payload.version,
                role=payload.role,
                status=payload.status,
            ),
        )
    )


@router.delete(
    "/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a Store membership",
    description=(
        "Atomically removes a pending, active, or suspended non-owner membership."
    ),
    dependencies=[require_permission("store:delete")],
    responses=_MUTATION_RESPONSES,
)
async def remove_store_member(
    store_id: UUID,
    member_id: UUID,
    identity: CurrentIdentity,
    service: StoreMembershipServiceDependency,
) -> Response:
    await service.remove(store_id, member_id, identity.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{member_id}/accept",
    response_model=StoreMembershipResponse,
    summary="Accept a Store invitation",
    description=(
        "Allows only the invited identity to accept a non-expired invitation "
        "using optimistic concurrency."
    ),
    dependencies=[require_permission("store:view")],
    responses=_MUTATION_RESPONSES,
)
async def accept_store_invitation(
    store_id: UUID,
    member_id: UUID,
    payload: StoreMembershipVersionRequest,
    identity: CurrentIdentity,
    service: StoreMembershipServiceDependency,
) -> StoreMembershipResponse:
    return _response(
        await service.accept(
            store_id,
            member_id,
            identity.user.id,
            payload.version,
        )
    )


@router.post(
    "/{member_id}/decline",
    response_model=StoreMembershipResponse,
    summary="Decline a Store invitation",
    description=(
        "Allows only the invited identity to decline a pending invitation "
        "using optimistic concurrency."
    ),
    dependencies=[require_permission("store:view")],
    responses=_MUTATION_RESPONSES,
)
async def decline_store_invitation(
    store_id: UUID,
    member_id: UUID,
    payload: StoreMembershipVersionRequest,
    identity: CurrentIdentity,
    service: StoreMembershipServiceDependency,
) -> StoreMembershipResponse:
    return _response(
        await service.decline(
            store_id,
            member_id,
            identity.user.id,
            payload.version,
        )
    )
