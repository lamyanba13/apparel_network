from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.stores.domain import StoreVerificationStatus


class StoreVerificationMetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_license: str | None = Field(
        default=None,
        max_length=200,
        examples=["MN-BUSINESS-2026-001"],
    )
    tax_registration: str | None = Field(
        default=None,
        max_length=200,
        examples=["14ABCDE1234F1Z5"],
    )
    owner_identity: str | None = Field(
        default=None,
        max_length=300,
        examples=["Identity checked against government-issued document"],
    )
    address_proof: str | None = Field(
        default=None,
        max_length=300,
        examples=["Municipal utility record dated 2026-07"],
    )
    additional_notes: str | None = Field(
        default=None,
        max_length=2000,
        examples=["Trading name differs from the registered entity name."],
    )


class StoreVerificationSubmitRequest(StoreVerificationMetadataRequest):
    pass


class StoreVerificationReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, examples=[1])
    review_notes: str | None = Field(
        default=None,
        max_length=4000,
        examples=["Registration references checked."],
    )


class StoreVerificationApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, examples=[2])


class StoreVerificationRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, examples=[2])
    rejection_reason: str = Field(
        min_length=1,
        max_length=1000,
        examples=["The submitted address proof does not match the Store address."],
    )
    review_notes: str | None = Field(
        default=None,
        max_length=4000,
        examples=["Submit a current address reference before reopening."],
    )


class StoreVerificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    metadata: StoreVerificationMetadataRequest
    version: int
    created_at: datetime
    updated_at: datetime
