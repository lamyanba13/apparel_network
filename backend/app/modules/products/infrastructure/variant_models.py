from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import (
    AuditFieldsMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionNumberMixin,
)


class ProductVariantModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint(
            "sort_order >= 0", name="product_variants_sort_order_nonnegative"
        ),
        CheckConstraint("version >= 1", name="product_variants_version_positive"),
        CheckConstraint(
            "char_length(attribute_signature) = 64",
            name="product_variants_signature_length",
        ),
        Index("ix_product_variants_product", "product_id"),
        Index("ix_product_variants_store", "store_id"),
        Index("ix_product_variants_product_order", "product_id", "sort_order"),
        Index(
            "uq_product_variants_store_reference",
            "store_id",
            "reference",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_product_variants_product_signature",
            "product_id",
            "attribute_signature",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    attribute_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default="true"
    )
