from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stores.application.verification_repositories import (
    StoreVerificationRepository,
)
from app.modules.stores.domain import (
    StoreVerification,
    StoreVerificationMetadata,
    StoreVerificationStatus,
)
from app.modules.stores.infrastructure.persistence.verification_models import (
    StoreVerificationModel,
)


class SqlAlchemyStoreVerificationRepository(StoreVerificationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        store_id: UUID,
        submitted_by_id: UUID,
        metadata: StoreVerificationMetadata,
        submitted_at: datetime,
    ) -> StoreVerification:
        model = StoreVerificationModel(
            store_id=store_id,
            submitted_by_id=submitted_by_id,
            status=StoreVerificationStatus.SUBMITTED,
            submitted_at=submitted_at,
            **_metadata_values(metadata),
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _verification(model)

    async def get_by_store_id(self, store_id: UUID) -> StoreVerification | None:
        model = await self._session.scalar(
            select(StoreVerificationModel).where(
                StoreVerificationModel.store_id == store_id
            )
        )
        return _verification(model) if model is not None else None

    async def reopen(
        self,
        store_id: UUID,
        *,
        submitted_by_id: UUID,
        metadata: StoreVerificationMetadata,
        submitted_at: datetime,
        expected_version: int,
    ) -> StoreVerification | None:
        return await self._conditional_update(
            store_id,
            expected_version=expected_version,
            expected_status=StoreVerificationStatus.REJECTED,
            values={
                "submitted_by_id": submitted_by_id,
                "status": StoreVerificationStatus.SUBMITTED,
                "submitted_at": submitted_at,
                "reviewed_by_id": None,
                "review_started_at": None,
                "reviewed_at": None,
                "rejection_reason": None,
                "review_notes": None,
                **_metadata_values(metadata),
            },
        )

    async def start_review(
        self,
        store_id: UUID,
        *,
        reviewed_by_id: UUID,
        review_notes: str | None,
        started_at: datetime,
        expected_version: int,
    ) -> StoreVerification | None:
        return await self._conditional_update(
            store_id,
            expected_version=expected_version,
            expected_status=StoreVerificationStatus.SUBMITTED,
            values={
                "status": StoreVerificationStatus.IN_REVIEW,
                "reviewed_by_id": reviewed_by_id,
                "review_started_at": started_at,
                "review_notes": review_notes,
            },
        )

    async def update_review(
        self,
        store_id: UUID,
        *,
        reviewed_by_id: UUID,
        review_notes: str | None,
        expected_version: int,
    ) -> StoreVerification | None:
        result = await self._session.execute(
            update(StoreVerificationModel)
            .where(
                StoreVerificationModel.store_id == store_id,
                StoreVerificationModel.status == StoreVerificationStatus.IN_REVIEW,
                StoreVerificationModel.reviewed_by_id == reviewed_by_id,
                StoreVerificationModel.version == expected_version,
            )
            .values(
                review_notes=review_notes,
                updated_at=func.now(),
                version=StoreVerificationModel.version + 1,
            )
            .returning(StoreVerificationModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _verification(model) if model is not None else None

    async def approve(
        self,
        store_id: UUID,
        *,
        reviewed_by_id: UUID,
        reviewed_at: datetime,
        expected_version: int,
    ) -> StoreVerification | None:
        return await self._conditional_update(
            store_id,
            expected_version=expected_version,
            expected_status=StoreVerificationStatus.IN_REVIEW,
            values={
                "status": StoreVerificationStatus.APPROVED,
                "reviewed_by_id": reviewed_by_id,
                "reviewed_at": reviewed_at,
                "rejection_reason": None,
            },
        )

    async def reject(
        self,
        store_id: UUID,
        *,
        reviewed_by_id: UUID,
        rejection_reason: str,
        review_notes: str | None,
        reviewed_at: datetime,
        expected_version: int,
    ) -> StoreVerification | None:
        return await self._conditional_update(
            store_id,
            expected_version=expected_version,
            expected_status=StoreVerificationStatus.IN_REVIEW,
            values={
                "status": StoreVerificationStatus.REJECTED,
                "reviewed_by_id": reviewed_by_id,
                "reviewed_at": reviewed_at,
                "rejection_reason": rejection_reason,
                "review_notes": review_notes,
            },
        )

    async def count_pending(self) -> int:
        count = await self._session.scalar(
            select(func.count())
            .select_from(StoreVerificationModel)
            .where(
                StoreVerificationModel.status.in_(
                    {
                        StoreVerificationStatus.SUBMITTED,
                        StoreVerificationStatus.IN_REVIEW,
                    }
                )
            )
        )
        return int(count or 0)

    async def _conditional_update(
        self,
        store_id: UUID,
        *,
        expected_version: int,
        expected_status: StoreVerificationStatus,
        values: dict[str, object],
    ) -> StoreVerification | None:
        result = await self._session.execute(
            update(StoreVerificationModel)
            .where(
                StoreVerificationModel.store_id == store_id,
                StoreVerificationModel.status == expected_status,
                StoreVerificationModel.version == expected_version,
            )
            .values(
                **values,
                updated_at=func.now(),
                version=StoreVerificationModel.version + 1,
            )
            .returning(StoreVerificationModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _verification(model) if model is not None else None


def _metadata_values(metadata: StoreVerificationMetadata) -> dict[str, object]:
    return {
        "business_license": metadata.business_license,
        "tax_registration": metadata.tax_registration,
        "owner_identity": metadata.owner_identity,
        "address_proof": metadata.address_proof,
        "additional_notes": metadata.additional_notes,
    }


def _verification(model: StoreVerificationModel) -> StoreVerification:
    return StoreVerification(
        id=model.id,
        store_id=model.store_id,
        submitted_by_id=model.submitted_by_id,
        reviewed_by_id=model.reviewed_by_id,
        status=model.status,
        submitted_at=model.submitted_at,
        review_started_at=model.review_started_at,
        reviewed_at=model.reviewed_at,
        rejection_reason=model.rejection_reason,
        review_notes=model.review_notes,
        metadata=StoreVerificationMetadata(
            business_license=model.business_license,
            tax_registration=model.tax_registration,
            owner_identity=model.owner_identity,
            address_proof=model.address_proof,
            additional_notes=model.additional_notes,
        ),
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
