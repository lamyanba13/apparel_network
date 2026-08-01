from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
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
from app.modules.products.domain import ProductStatus, ProductVisibility


class ProductModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("catalog_id", "slug", name="uq_products_catalog_slug"),
        UniqueConstraint("store_id", "sku", name="uq_products_store_sku"),
        CheckConstraint("version >= 1", name="products_version_positive"),
        CheckConstraint("sort_order >= 0", name="products_sort_order_non_negative"),
        CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'",
            name="products_deleted_archived",
        ),
        CheckConstraint(
            "char_length(name) BETWEEN 2 AND 200", name="products_name_length"
        ),
        Index("ix_products_store_id", "store_id"),
        Index("ix_products_catalog_id", "catalog_id"),
        Index("ix_products_catalog_status", "catalog_id", "status"),
        Index("ix_products_store_status", "store_id", "status"),
        Index("ix_products_store_visibility", "store_id", "visibility"),
        Index("ix_products_sku", "sku"),
        Index("ix_products_slug", "slug"),
    )
    catalog_id: Mapped[UUID] = mapped_column(
        ForeignKey("catalogs.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(
            ProductStatus,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        default=ProductStatus.DRAFT,
        server_default=ProductStatus.DRAFT.value,
        nullable=False,
    )
    visibility: Mapped[ProductVisibility] = mapped_column(
        Enum(
            ProductVisibility,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        default=ProductVisibility.PRIVATE,
        server_default=ProductVisibility.PRIVATE.value,
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sort_order: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
