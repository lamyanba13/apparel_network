from dataclasses import dataclass

from app.modules.stores.domain import StoreVerificationMetadata


@dataclass(frozen=True, slots=True)
class StoreVerificationSubmission:
    metadata: StoreVerificationMetadata


@dataclass(frozen=True, slots=True)
class StoreVerificationReview:
    expected_version: int
    review_notes: str | None = None


@dataclass(frozen=True, slots=True)
class StoreVerificationApproval:
    expected_version: int


@dataclass(frozen=True, slots=True)
class StoreVerificationRejection:
    expected_version: int
    rejection_reason: str
    review_notes: str | None = None
