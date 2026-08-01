from __future__ import annotations

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
from app.modules.catalogs.domain.taxonomy import (
    CategoryStatus,
    CollectionStatus,
    CollectionType,
    Visibility,
)


class CategoryModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("store_id", "slug", name="uq_categories_store_slug"),
        CheckConstraint("version >= 1", name="categories_version_positive"),
        CheckConstraint("sort_order >= 0", name="categories_sort_order_non_negative"),
        CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'",
            name="categories_deleted_archived",
        ),
        Index("ix_categories_store_id", "store_id"),
        Index("ix_categories_parent", "parent_category_id"),
        Index("ix_categories_status", "status"),
        Index("ix_categories_visibility", "visibility"),
        Index("ix_categories_slug", "slug"),
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    status: Mapped[CategoryStatus] = mapped_column(
        Enum(
            CategoryStatus,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        default=CategoryStatus.DRAFT,
        server_default=CategoryStatus.DRAFT.value,
        nullable=False,
    )
    visibility: Mapped[Visibility] = mapped_column(
        Enum(
            Visibility,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        default=Visibility.PRIVATE,
        server_default=Visibility.PRIVATE.value,
        nullable=False,
    )


class ProductCategoryModel(Base):
    __tablename__ = "product_categories"
    __table_args__ = (
        Index("ix_product_categories_product", "product_id"),
        Index("ix_product_categories_category", "category_id"),
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )


class CollectionModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("store_id", "slug", name="uq_collections_store_slug"),
        CheckConstraint("version >= 1", name="collections_version_positive"),
        CheckConstraint("sort_order >= 0", name="collections_sort_order_non_negative"),
        CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'",
            name="collections_deleted_archived",
        ),
        Index("ix_collections_store_id", "store_id"),
        Index("ix_collections_status", "status"),
        Index("ix_collections_visibility", "visibility"),
        Index("ix_collections_slug", "slug"),
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    status: Mapped[CollectionStatus] = mapped_column(
        Enum(
            CollectionStatus,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        default=CollectionStatus.DRAFT,
        server_default=CollectionStatus.DRAFT.value,
        nullable=False,
    )
    collection_type: Mapped[CollectionType] = mapped_column(
        Enum(
            CollectionType,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        default=CollectionType.MANUAL,
        server_default=CollectionType.MANUAL.value,
        nullable=False,
    )
    visibility: Mapped[Visibility] = mapped_column(
        Enum(
            Visibility,
            native_enum=False,
            values_callable=lambda values: [v.value for v in values],
        ),
        default=Visibility.PRIVATE,
        server_default=Visibility.PRIVATE.value,
        nullable=False,
    )


class CollectionProductModel(Base):
    __tablename__ = "collection_products"
    __table_args__ = (
        CheckConstraint(
            "display_order >= 0", name="collection_products_order_non_negative"
        ),
        Index("ix_collection_products_collection", "collection_id"),
        Index("ix_collection_products_product", "product_id"),
    )
    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
