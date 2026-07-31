from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class StoreVerificationStatus(StrEnum):
    """Review lifecycle for one Store verification record."""

    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class StoreVerificationMetadata:
    """Structured references supplied without owning uploaded documents."""

    business_license: str | None = None
    tax_registration: str | None = None
    owner_identity: str | None = None
    address_proof: str | None = None
    additional_notes: str | None = None


@dataclass(frozen=True, slots=True)
class StoreVerification:
    id: UUID
    store_id: UUID
    submitted_by_id: UUID
    reviewed_by_id: UUID | None
    status: StoreVerificationStatus
    submitted_at: datetime
    review_started_at: datetime | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    review_notes: str | None
    metadata: StoreVerificationMetadata
    version: int
    created_at: datetime
    updated_at: datetime
