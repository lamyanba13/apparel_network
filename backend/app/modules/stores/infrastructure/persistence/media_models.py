from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    false,
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
from app.modules.stores.domain import StoreMediaStatus, StoreMediaType


class StoreMediaModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    Base,
):
    __tablename__ = "store_media"
    __table_args__ = (
        UniqueConstraint("object_key", name="object_key_unique"),
        CheckConstraint("file_size > 0", name="file_size_positive"),
        CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
        CheckConstraint("orientation BETWEEN 1 AND 8", name="orientation_valid"),
        CheckConstraint("aspect_ratio > 0", name="aspect_ratio_positive"),
        CheckConstraint("display_order >= 0", name="display_order_nonnegative"),
        CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="checksum_sha256_valid",
        ),
        CheckConstraint(
            "(status = 'deleted' AND deleted_at IS NOT NULL) OR "
            "(status <> 'deleted' AND deleted_at IS NULL)",
            name="soft_delete_consistent",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_store_media_store_id", "store_id"),
        Index("ix_store_media_media_type", "media_type"),
        Index("ix_store_media_display_order", "display_order"),
        Index("ix_store_media_status", "status"),
        Index("ix_store_media_uploaded_by", "uploaded_by"),
        Index(
            "ix_store_media_active_store_type_order",
            "store_id",
            "media_type",
            "display_order",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_store_media_not_deleted",
            "store_id",
            "created_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_store_media_active_logo",
            "store_id",
            unique=True,
            postgresql_where=text(
                "media_type = 'logo' AND status = 'active' " "AND deleted_at IS NULL"
            ),
        ),
        Index(
            "uq_store_media_active_banner",
            "store_id",
            unique=True,
            postgresql_where=text(
                "media_type = 'banner' AND status = 'active' " "AND deleted_at IS NULL"
            ),
        ),
        Index(
            "uq_store_media_checksum",
            "store_id",
            "checksum_sha256",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploaded_by_id: Mapped[UUID] = mapped_column(
        "uploaded_by",
        ForeignKey("identity_users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    media_type: Mapped[StoreMediaType] = mapped_column(
        Enum(
            StoreMediaType,
            name="store_media_type",
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    status: Mapped[StoreMediaStatus] = mapped_column(
        Enum(
            StoreMediaStatus,
            name="store_media_status",
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=StoreMediaStatus.ACTIVE,
        server_default=StoreMediaStatus.ACTIVE.value,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(10), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    orientation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    aspect_ratio: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
    )
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    etag: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
