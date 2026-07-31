from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionNumberMixin,
)
from app.modules.stores.domain import StoreStatus, VerificationStatus


class StoreModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    Base,
):
    __tablename__ = "stores"
    __table_args__ = (
        UniqueConstraint("slug", name="slug_unique"),
        CheckConstraint("char_length(name) BETWEEN 2 AND 150", name="name_length"),
        CheckConstraint(
            "slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'",
            name="slug_canonical",
        ),
        CheckConstraint(
            "description IS NULL OR char_length(description) <= 2000",
            name="description_length",
        ),
        CheckConstraint(
            "char_length(phone) BETWEEN 7 AND 32",
            name="phone_length",
        ),
        CheckConstraint(
            "char_length(email) BETWEEN 3 AND 320",
            name="email_length",
        ),
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name="coordinates_complete",
        ),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="longitude_range",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_stores_owner_id_status", "owner_id", "status"),
        Index("ix_stores_status_verification", "status", "verification_status"),
        Index(
            "ix_stores_active_public",
            "verification_status",
            postgresql_where=text("deleted_at IS NULL AND status = 'active'"),
        ),
    )

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    website: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    district: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )
    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6),
        nullable=True,
    )
    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    banner_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[StoreStatus] = mapped_column(
        Enum(
            StoreStatus,
            name="store_status",
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=StoreStatus.DRAFT,
        server_default=StoreStatus.DRAFT.value,
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(
            VerificationStatus,
            name="store_verification_status",
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=VerificationStatus.UNVERIFIED,
        server_default=VerificationStatus.UNVERIFIED.value,
    )
