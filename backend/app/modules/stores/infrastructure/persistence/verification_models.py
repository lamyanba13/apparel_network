from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import (
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionNumberMixin,
)
from app.modules.stores.domain import StoreVerificationStatus


class StoreVerificationModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    VersionNumberMixin,
    Base,
):
    __tablename__ = "store_verifications"
    __table_args__ = (
        UniqueConstraint("store_id", name="store_verifications_store_unique"),
        CheckConstraint(
            "char_length(business_license) <= 200",
            name="business_license_length",
        ),
        CheckConstraint(
            "char_length(tax_registration) <= 200",
            name="tax_registration_length",
        ),
        CheckConstraint(
            "char_length(owner_identity) <= 300",
            name="owner_identity_length",
        ),
        CheckConstraint(
            "char_length(address_proof) <= 300",
            name="address_proof_length",
        ),
        CheckConstraint(
            "char_length(additional_notes) <= 2000",
            name="additional_notes_length",
        ),
        CheckConstraint(
            "char_length(review_notes) <= 4000",
            name="review_notes_length",
        ),
        CheckConstraint(
            "rejection_reason IS NULL OR "
            "char_length(btrim(rejection_reason)) BETWEEN 1 AND 1000",
            name="rejection_reason_length",
        ),
        CheckConstraint(
            "("
            "status = 'submitted' AND reviewed_by_id IS NULL "
            "AND review_started_at IS NULL AND reviewed_at IS NULL "
            "AND rejection_reason IS NULL"
            ") OR ("
            "status = 'in_review' AND reviewed_by_id IS NOT NULL "
            "AND review_started_at IS NOT NULL AND reviewed_at IS NULL "
            "AND rejection_reason IS NULL"
            ") OR ("
            "status = 'approved' AND reviewed_by_id IS NOT NULL "
            "AND review_started_at IS NOT NULL AND reviewed_at IS NOT NULL "
            "AND rejection_reason IS NULL"
            ") OR ("
            "status = 'rejected' AND reviewed_by_id IS NOT NULL "
            "AND review_started_at IS NOT NULL AND reviewed_at IS NOT NULL "
            "AND rejection_reason IS NOT NULL"
            ")",
            name="lifecycle_consistent",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index(
            "ix_store_verifications_status_submitted_at",
            "status",
            "submitted_at",
        ),
        Index(
            "ix_store_verifications_pending",
            "submitted_at",
            postgresql_where=text("status IN ('submitted', 'in_review')"),
        ),
        Index(
            "ix_store_verifications_reviewed_by_status",
            "reviewed_by_id",
            "status",
        ),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
    )
    submitted_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewed_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[StoreVerificationStatus] = mapped_column(
        Enum(
            StoreVerificationStatus,
            name="store_verification_workflow_status",
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=StoreVerificationStatus.SUBMITTED,
        server_default=StoreVerificationStatus.SUBMITTED.value,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    review_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_license: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tax_registration: Mapped[str | None] = mapped_column(String(200), nullable=True)
    owner_identity: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address_proof: Mapped[str | None] = mapped_column(String(300), nullable=True)
    additional_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
