from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import (
    AuditFieldsMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionNumberMixin,
)
from app.modules.products.domain.media import ProductMediaRole, ProductMediaType


class ProductMediaModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "product_media"
    __table_args__ = (
        UniqueConstraint("object_key", name="uq_product_media_object_key"),
        CheckConstraint("file_size > 0", name="product_media_file_size_positive"),
        CheckConstraint(
            "(width IS NULL OR width > 0) AND (height IS NULL OR height > 0)",
            name="product_media_dimensions_positive",
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds > 0",
            name="product_media_duration_positive",
        ),
        CheckConstraint(
            "display_order >= 0", name="product_media_display_order_nonnegative"
        ),
        CheckConstraint("version >= 1", name="product_media_version_positive"),
        CheckConstraint(
            "deleted_at IS NULL OR is_active = false",
            name="product_media_soft_delete_consistent",
        ),
        Index("ix_product_media_product", "product_id"),
        Index("ix_product_media_store", "store_id"),
        Index("ix_product_media_catalog", "catalog_id"),
        Index("ix_product_media_product_role", "product_id", "role"),
        Index("ix_product_media_product_order", "product_id", "display_order"),
        Index(
            "uq_product_media_primary",
            "product_id",
            unique=True,
            postgresql_where=text(
                "role = 'primary' AND media_type = 'image' AND "
                "is_active = true AND deleted_at IS NULL"
            ),
        ),
        Index(
            "uq_product_media_checksum",
            "product_id",
            "checksum_sha256",
            unique=True,
            postgresql_where=text("is_active = true AND deleted_at IS NULL"),
        ),
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    catalog_id: Mapped[UUID] = mapped_column(
        ForeignKey("catalogs.id", ondelete="RESTRICT"), nullable=False
    )
    media_type: Mapped[ProductMediaType] = mapped_column(
        Enum(
            ProductMediaType,
            native_enum=False,
            values_callable=lambda v: [x.value for x in v],
        ),
        nullable=False,
    )
    role: Mapped[ProductMediaRole] = mapped_column(
        Enum(
            ProductMediaRole,
            native_enum=False,
            values_callable=lambda v: [x.value for x in v],
        ),
        nullable=False,
    )
    storage_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="minio", server_default="minio"
    )
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    extension: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    display_order: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
