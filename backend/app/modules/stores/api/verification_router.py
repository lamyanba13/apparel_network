from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.stores.api.dependencies import (
    StoreVerificationServiceDependency,
)
from app.modules.stores.api.verification_schemas import (
    StoreVerificationApproveRequest,
    StoreVerificationMetadataRequest,
    StoreVerificationRejectRequest,
    StoreVerificationResponse,
    StoreVerificationReviewRequest,
    StoreVerificationSubmitRequest,
)
from app.modules.stores.application.verification_schemas import (
    StoreVerificationApproval,
    StoreVerificationRejection,
    StoreVerificationReview,
    StoreVerificationSubmission,
)
from app.modules.stores.domain import StoreVerification, StoreVerificationMetadata

router = APIRouter(
    prefix="/stores/{store_id}/verification",
    tags=["Store Verification"],
)

_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required permission"},
}
_RESOURCE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_AUTH_RESPONSES,
    404: {"description": "Store or Store verification not found"},
}
_MUTATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_RESOURCE_RESPONSES,
    409: {"description": "Invalid lifecycle state or stale version"},
}


def _response(
    value: StoreVerification,
    *,
    include_private_review: bool = False,
) -> StoreVerificationResponse:
    return StoreVerificationResponse(
        id=value.id,
        store_id=value.store_id,
        submitted_by_id=value.submitted_by_id,
        reviewed_by_id=(value.reviewed_by_id if include_private_review else None),
        status=value.status,
        submitted_at=value.submitted_at,
        review_started_at=value.review_started_at,
        reviewed_at=value.reviewed_at,
        rejection_reason=value.rejection_reason,
        review_notes=value.review_notes if include_private_review else None,
        metadata=StoreVerificationMetadataRequest(
            business_license=value.metadata.business_license,
            tax_registration=value.metadata.tax_registration,
            owner_identity=value.metadata.owner_identity,
            address_proof=value.metadata.address_proof,
            additional_notes=value.metadata.additional_notes,
        ),
        version=value.version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _metadata(payload: StoreVerificationSubmitRequest) -> StoreVerificationMetadata:
    return StoreVerificationMetadata(
        business_license=payload.business_license,
        tax_registration=payload.tax_registration,
        owner_identity=payload.owner_identity,
        address_proof=payload.address_proof,
        additional_notes=payload.additional_notes,
    )


@router.post(
    "/submit",
    response_model=StoreVerificationResponse,
    summary="Submit or reopen Store verification",
    description=(
        "Submits an owned draft Store for verification. Repeating an identical "
        "open submission is idempotent; a rejected verification may be reopened."
    ),
    dependencies=[require_permission("store:update")],
    responses=_MUTATION_RESPONSES,
)
async def submit_store_verification(
    store_id: UUID,
    payload: StoreVerificationSubmitRequest,
    identity: CurrentIdentity,
    service: StoreVerificationServiceDependency,
) -> StoreVerificationResponse:
    return _response(
        await service.submit(
            store_id,
            identity.user.id,
            StoreVerificationSubmission(metadata=_metadata(payload)),
        )
    )


@router.get(
    "",
    response_model=StoreVerificationResponse,
    summary="Get owned Store verification",
    description="Returns verification state for a Store owned by the identity.",
    dependencies=[require_permission("store:view")],
    responses=_RESOURCE_RESPONSES,
)
async def get_store_verification(
    store_id: UUID,
    identity: CurrentIdentity,
    service: StoreVerificationServiceDependency,
) -> StoreVerificationResponse:
    return _response(await service.get_owned(store_id, identity.user.id))


@router.patch(
    "/review",
    response_model=StoreVerificationResponse,
    summary="Start or update a Store verification review",
    description=(
        "Starts an administrative review or updates notes for the assigned "
        "reviewer using optimistic concurrency."
    ),
    dependencies=[require_permission("admin:access")],
    responses=_MUTATION_RESPONSES,
)
async def review_store_verification(
    store_id: UUID,
    payload: StoreVerificationReviewRequest,
    identity: CurrentIdentity,
    service: StoreVerificationServiceDependency,
) -> StoreVerificationResponse:
    return _response(
        await service.review(
            store_id,
            identity.user.id,
            StoreVerificationReview(
                expected_version=payload.version,
                review_notes=payload.review_notes,
            ),
        ),
        include_private_review=True,
    )


@router.post(
    "/approve",
    response_model=StoreVerificationResponse,
    summary="Approve Store verification",
    description=(
        "Atomically approves an in-review verification and activates the Store."
    ),
    dependencies=[require_permission("admin:access")],
    responses=_MUTATION_RESPONSES,
)
async def approve_store_verification(
    store_id: UUID,
    payload: StoreVerificationApproveRequest,
    identity: CurrentIdentity,
    service: StoreVerificationServiceDependency,
) -> StoreVerificationResponse:
    return _response(
        await service.approve(
            store_id,
            identity.user.id,
            StoreVerificationApproval(expected_version=payload.version),
        ),
        include_private_review=True,
    )


@router.post(
    "/reject",
    response_model=StoreVerificationResponse,
    summary="Reject Store verification",
    description=(
        "Atomically rejects an in-review verification with a required reason "
        "and returns the Store to draft for correction."
    ),
    dependencies=[require_permission("admin:access")],
    responses=_MUTATION_RESPONSES,
)
async def reject_store_verification(
    store_id: UUID,
    payload: StoreVerificationRejectRequest,
    identity: CurrentIdentity,
    service: StoreVerificationServiceDependency,
) -> StoreVerificationResponse:
    return _response(
        await service.reject(
            store_id,
            identity.user.id,
            StoreVerificationRejection(
                expected_version=payload.version,
                rejection_reason=payload.rejection_reason,
                review_notes=payload.review_notes,
            ),
        ),
        include_private_review=True,
    )
