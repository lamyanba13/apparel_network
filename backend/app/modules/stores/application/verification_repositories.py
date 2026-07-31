from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.stores.domain import StoreVerification, StoreVerificationMetadata


class StoreVerificationRepository(Protocol):
    async def add(
        self,
        *,
        store_id: UUID,
        submitted_by_id: UUID,
        metadata: StoreVerificationMetadata,
        submitted_at: datetime,
    ) -> StoreVerification: ...

    async def get_by_store_id(self, store_id: UUID) -> StoreVerification | None: ...

    async def reopen(
        self,
        store_id: UUID,
        *,
        submitted_by_id: UUID,
        metadata: StoreVerificationMetadata,
        submitted_at: datetime,
        expected_version: int,
    ) -> StoreVerification | None: ...

    async def start_review(
        self,
        store_id: UUID,
        *,
        reviewed_by_id: UUID,
        review_notes: str | None,
        started_at: datetime,
        expected_version: int,
    ) -> StoreVerification | None: ...

    async def update_review(
        self,
        store_id: UUID,
        *,
        reviewed_by_id: UUID,
        review_notes: str | None,
        expected_version: int,
    ) -> StoreVerification | None: ...

    async def approve(
        self,
        store_id: UUID,
        *,
        reviewed_by_id: UUID,
        reviewed_at: datetime,
        expected_version: int,
    ) -> StoreVerification | None: ...

    async def reject(
        self,
        store_id: UUID,
        *,
        reviewed_by_id: UUID,
        rejection_reason: str,
        review_notes: str | None,
        reviewed_at: datetime,
        expected_version: int,
    ) -> StoreVerification | None: ...

    async def count_pending(self) -> int: ...
