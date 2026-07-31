from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.common.context import maybe_get_request_context
from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.stores.application.repositories import StoreRepository
from app.modules.stores.application.verification_repositories import (
    StoreVerificationRepository,
)
from app.modules.stores.application.verification_schemas import (
    StoreVerificationApproval,
    StoreVerificationRejection,
    StoreVerificationReview,
    StoreVerificationSubmission,
)
from app.modules.stores.domain import (
    Store,
    StoreStatus,
    StoreVerification,
    StoreVerificationMetadata,
    StoreVerificationRejected,
    StoreVerificationReopened,
    StoreVerificationStarted,
    StoreVerificationStatus,
    StoreVerificationSubmitted,
    StoreVerified,
    VerificationStatus,
)
from app.observability.metrics import (
    STORE_VERIFICATION_APPROVED,
    STORE_VERIFICATION_PENDING,
    STORE_VERIFICATION_REJECTED,
    STORE_VERIFICATION_SUBMITTED,
    STORES_ACTIVE,
    STORES_VERIFIED,
)


class VerificationPolicyService:
    """Normalize evidence metadata and enforce lifecycle preconditions."""

    def submission(
        self,
        value: StoreVerificationSubmission,
    ) -> StoreVerificationSubmission:
        metadata = StoreVerificationMetadata(
            business_license=self._optional(
                value.metadata.business_license,
                "business_license",
                200,
            ),
            tax_registration=self._optional(
                value.metadata.tax_registration,
                "tax_registration",
                200,
            ),
            owner_identity=self._optional(
                value.metadata.owner_identity,
                "owner_identity",
                300,
            ),
            address_proof=self._optional(
                value.metadata.address_proof,
                "address_proof",
                300,
            ),
            additional_notes=self._optional(
                value.metadata.additional_notes,
                "additional_notes",
                2000,
            ),
        )
        evidence = (
            metadata.business_license,
            metadata.tax_registration,
            metadata.owner_identity,
            metadata.address_proof,
        )
        if not any(evidence):
            raise _validation_error(
                "metadata",
                "At least one verification reference is required.",
            )
        return StoreVerificationSubmission(metadata=metadata)

    def review(self, value: StoreVerificationReview) -> StoreVerificationReview:
        return StoreVerificationReview(
            expected_version=value.expected_version,
            review_notes=self._optional(value.review_notes, "review_notes", 4000),
        )

    def rejection(
        self,
        value: StoreVerificationRejection,
    ) -> StoreVerificationRejection:
        reason = " ".join(value.rejection_reason.split())
        if not 1 <= len(reason) <= 1000:
            raise _validation_error(
                "rejection_reason",
                "Rejection reason must contain 1 to 1000 characters.",
            )
        return StoreVerificationRejection(
            expected_version=value.expected_version,
            rejection_reason=reason,
            review_notes=self._optional(value.review_notes, "review_notes", 4000),
        )

    def require_submittable(self, store: Store) -> None:
        if store.status is not StoreStatus.DRAFT or store.verification_status not in {
            VerificationStatus.UNVERIFIED,
            VerificationStatus.REJECTED,
        }:
            raise _conflict("The Store is not eligible for verification submission.")

    def require_reviewable(self, verification: StoreVerification) -> None:
        if verification.status not in {
            StoreVerificationStatus.SUBMITTED,
            StoreVerificationStatus.IN_REVIEW,
        }:
            raise _conflict("The verification is not open for review.")

    def _optional(
        self,
        value: str | None,
        field: str,
        maximum: int,
    ) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            return None
        if len(normalized) > maximum:
            raise _validation_error(
                field,
                f"{field.replace('_', ' ').title()} cannot exceed "
                f"{maximum} characters.",
            )
        return normalized


class VerificationAuditService:
    """Publish safe verification audit events through the shared event port."""

    def __init__(self, events: EventPublisher) -> None:
        self._events = events

    async def submitted(
        self,
        verification: StoreVerification,
        actor_user_id: UUID,
    ) -> None:
        await self._events.publish(
            StoreVerificationSubmitted(
                verification_id=verification.id,
                store_id=verification.store_id,
                actor_user_id=actor_user_id,
                status=verification.status,
                correlation_id=_correlation_id(),
            )
        )

    async def reopened(
        self,
        verification: StoreVerification,
        actor_user_id: UUID,
    ) -> None:
        await self._events.publish(
            StoreVerificationReopened(
                verification_id=verification.id,
                store_id=verification.store_id,
                actor_user_id=actor_user_id,
                status=verification.status,
                correlation_id=_correlation_id(),
            )
        )

    async def started(
        self,
        verification: StoreVerification,
        actor_user_id: UUID,
    ) -> None:
        await self._events.publish(
            StoreVerificationStarted(
                verification_id=verification.id,
                store_id=verification.store_id,
                actor_user_id=actor_user_id,
                status=verification.status,
                correlation_id=_correlation_id(),
            )
        )

    async def approved(
        self,
        store: Store,
        verification: StoreVerification,
        actor_user_id: UUID,
    ) -> None:
        await self._events.publish(
            StoreVerified(
                store_id=store.id,
                owner_id=store.owner_id,
                status=store.status,
                verification_status=store.verification_status,
                verification_id=verification.id,
                actor_user_id=actor_user_id,
                correlation_id=_correlation_id(),
            )
        )

    async def rejected(
        self,
        verification: StoreVerification,
        actor_user_id: UUID,
    ) -> None:
        await self._events.publish(
            StoreVerificationRejected(
                verification_id=verification.id,
                store_id=verification.store_id,
                actor_user_id=actor_user_id,
                status=verification.status,
                correlation_id=_correlation_id(),
            )
        )


class VerificationLifecycleService:
    """Coordinate verification and Store state changes in one transaction."""

    def __init__(
        self,
        verifications: StoreVerificationRepository,
        stores: StoreRepository,
        policy: VerificationPolicyService,
        audit: VerificationAuditService,
    ) -> None:
        self._verifications = verifications
        self._stores = stores
        self._policy = policy
        self._audit = audit

    async def submit(
        self,
        store: Store,
        actor_user_id: UUID,
        submission: StoreVerificationSubmission,
    ) -> StoreVerification:
        value = self._policy.submission(submission)
        current = await self._verifications.get_by_store_id(store.id)
        if current is not None and current.status in {
            StoreVerificationStatus.SUBMITTED,
            StoreVerificationStatus.IN_REVIEW,
        }:
            if current.metadata == value.metadata:
                return current
            raise _conflict("A verification submission is already open.")
        if current is not None and current.status is StoreVerificationStatus.APPROVED:
            raise _conflict("The Store verification is already approved.")

        self._policy.require_submittable(store)
        now = datetime.now(UTC)
        reopened = current is not None
        if current is None:
            verification = await self._verifications.add(
                store_id=store.id,
                submitted_by_id=actor_user_id,
                metadata=value.metadata,
                submitted_at=now,
            )
        else:
            reopened_verification = await self._verifications.reopen(
                store.id,
                submitted_by_id=actor_user_id,
                metadata=value.metadata,
                submitted_at=now,
                expected_version=current.version,
            )
            if reopened_verification is None:
                raise _conflict("The verification changed during submission.")
            verification = reopened_verification

        transitioned = await self._stores.transition(
            store.id,
            from_statuses=frozenset({StoreStatus.DRAFT}),
            status=StoreStatus.PENDING_REVIEW,
            verification_status=VerificationStatus.PENDING,
        )
        if transitioned is None:
            raise _conflict("The Store changed during verification submission.")

        STORE_VERIFICATION_SUBMITTED.inc()
        if reopened:
            await self._audit.reopened(verification, actor_user_id)
        else:
            await self._audit.submitted(verification, actor_user_id)
        await self._snapshot_metrics()
        return verification

    async def review(
        self,
        store_id: UUID,
        reviewer_id: UUID,
        review: StoreVerificationReview,
    ) -> StoreVerification:
        value = self._policy.review(review)
        current = await self._required(store_id)
        self._policy.require_reviewable(current)
        if current.status is StoreVerificationStatus.IN_REVIEW:
            if (
                current.reviewed_by_id == reviewer_id
                and current.review_notes == value.review_notes
            ):
                return current
            if current.reviewed_by_id != reviewer_id:
                raise _conflict("The verification is assigned to another reviewer.")
            updated = await self._verifications.update_review(
                store_id,
                reviewed_by_id=reviewer_id,
                review_notes=value.review_notes,
                expected_version=value.expected_version,
            )
            if updated is None:
                raise _conflict("The verification changed during review.")
            return updated

        started = await self._verifications.start_review(
            store_id,
            reviewed_by_id=reviewer_id,
            review_notes=value.review_notes,
            started_at=datetime.now(UTC),
            expected_version=value.expected_version,
        )
        if started is None:
            raise _conflict("The verification changed before review started.")
        await self._audit.started(started, reviewer_id)
        return started

    async def approve(
        self,
        store_id: UUID,
        reviewer_id: UUID,
        approval: StoreVerificationApproval,
    ) -> StoreVerification:
        current = await self._required(store_id)
        if current.status is StoreVerificationStatus.APPROVED:
            return current
        if current.status is not StoreVerificationStatus.IN_REVIEW:
            raise _conflict("Only an in-review verification can be approved.")
        approved = await self._verifications.approve(
            store_id,
            reviewed_by_id=reviewer_id,
            reviewed_at=datetime.now(UTC),
            expected_version=approval.expected_version,
        )
        if approved is None:
            raise _conflict("The verification changed before approval.")
        store = await self._stores.transition(
            store_id,
            from_statuses=frozenset({StoreStatus.PENDING_REVIEW}),
            status=StoreStatus.ACTIVE,
            verification_status=VerificationStatus.VERIFIED,
        )
        if store is None:
            raise _conflict("The Store changed before verification approval.")
        STORE_VERIFICATION_APPROVED.inc()
        await self._audit.approved(store, approved, reviewer_id)
        await self._snapshot_metrics()
        return approved

    async def reject(
        self,
        store_id: UUID,
        reviewer_id: UUID,
        rejection: StoreVerificationRejection,
    ) -> StoreVerification:
        value = self._policy.rejection(rejection)
        current = await self._required(store_id)
        if current.status is StoreVerificationStatus.REJECTED:
            if (
                current.rejection_reason == value.rejection_reason
                and current.review_notes == value.review_notes
            ):
                return current
            raise _conflict("The verification has already been rejected.")
        if current.status is not StoreVerificationStatus.IN_REVIEW:
            raise _conflict("Only an in-review verification can be rejected.")
        rejected = await self._verifications.reject(
            store_id,
            reviewed_by_id=reviewer_id,
            rejection_reason=value.rejection_reason,
            review_notes=value.review_notes,
            reviewed_at=datetime.now(UTC),
            expected_version=value.expected_version,
        )
        if rejected is None:
            raise _conflict("The verification changed before rejection.")
        store = await self._stores.transition(
            store_id,
            from_statuses=frozenset({StoreStatus.PENDING_REVIEW}),
            status=StoreStatus.DRAFT,
            verification_status=VerificationStatus.REJECTED,
        )
        if store is None:
            raise _conflict("The Store changed before verification rejection.")
        STORE_VERIFICATION_REJECTED.inc()
        await self._audit.rejected(rejected, reviewer_id)
        await self._snapshot_metrics()
        return rejected

    async def _required(self, store_id: UUID) -> StoreVerification:
        verification = await self._verifications.get_by_store_id(store_id)
        if verification is None:
            raise _not_found()
        return verification

    async def _snapshot_metrics(self) -> None:
        pending = await self._verifications.count_pending()
        active, verified = await self._stores.count_active_and_verified()
        STORE_VERIFICATION_PENDING.set(pending)
        STORES_ACTIVE.set(active)
        STORES_VERIFIED.set(verified)


class StoreVerificationService:
    """Owner and reviewer-facing Store Verification use cases."""

    def __init__(
        self,
        stores: StoreRepository,
        verifications: StoreVerificationRepository,
        lifecycle: VerificationLifecycleService,
    ) -> None:
        self._stores = stores
        self._verifications = verifications
        self._lifecycle = lifecycle

    async def submit(
        self,
        store_id: UUID,
        owner_id: UUID,
        submission: StoreVerificationSubmission,
    ) -> StoreVerification:
        store = await self._stores.get_for_owner(store_id, owner_id)
        if store is None:
            raise _store_not_found()
        return await self._lifecycle.submit(store, owner_id, submission)

    async def get_owned(self, store_id: UUID, owner_id: UUID) -> StoreVerification:
        store = await self._stores.get_for_owner(store_id, owner_id)
        if store is None:
            raise _store_not_found()
        verification = await self._verifications.get_by_store_id(store.id)
        if verification is None:
            raise _not_found()
        return verification

    async def review(
        self,
        store_id: UUID,
        reviewer_id: UUID,
        review: StoreVerificationReview,
    ) -> StoreVerification:
        await self._require_store(store_id)
        return await self._lifecycle.review(store_id, reviewer_id, review)

    async def approve(
        self,
        store_id: UUID,
        reviewer_id: UUID,
        approval: StoreVerificationApproval,
    ) -> StoreVerification:
        await self._require_store(store_id)
        return await self._lifecycle.approve(store_id, reviewer_id, approval)

    async def reject(
        self,
        store_id: UUID,
        reviewer_id: UUID,
        rejection: StoreVerificationRejection,
    ) -> StoreVerification:
        await self._require_store(store_id)
        return await self._lifecycle.reject(store_id, reviewer_id, rejection)

    async def _require_store(self, store_id: UUID) -> None:
        if await self._stores.get_by_id(store_id) is None:
            raise _store_not_found()


def _store_not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Store not found",
        detail="The requested store was not found.",
        status_code=404,
    )


def _not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Store verification not found",
        detail="The requested Store verification was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Store verification conflict",
        detail=detail,
        status_code=409,
    )


def _validation_error(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Store verification validation failed",
        detail="One or more Store verification fields are invalid.",
        status_code=422,
        errors=[
            FieldError(
                field=field,
                code="invalid_store_verification_field",
                message=message,
            )
        ],
    )


def _correlation_id() -> UUID | None:
    context = maybe_get_request_context()
    return context.correlation_id if context is not None else None
