from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import (
    AuditFieldsMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionNumberMixin,
)
from app.modules.products.domain import AttributeStatus, AttributeType, OutboxStatus


class ProductAttributeModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "product_attributes"
    __table_args__ = (
        UniqueConstraint("store_id", "slug", name="uq_product_attributes_store_slug"),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'",
            name="deleted_archived",
        ),
        Index("ix_product_attributes_store", "store_id"),
        Index("ix_product_attributes_status", "status"),
        Index("ix_product_attributes_type", "type"),
        Index("ix_product_attributes_order", "store_id", "sort_order"),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    attribute_type: Mapped[AttributeType] = mapped_column(
        "type",
        Enum(
            AttributeType,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    required: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    filterable: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    searchable: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[AttributeStatus] = mapped_column(
        Enum(
            AttributeStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=AttributeStatus.ACTIVE,
        server_default=AttributeStatus.ACTIVE.value,
    )
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class ProductAttributeValueModel(
    UuidPrimaryKeyMixin, TimestampMixin, VersionNumberMixin, Base
):
    __tablename__ = "product_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "attribute_id", "slug", name="uq_product_attribute_values_attribute_slug"
        ),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_product_attribute_values_attribute", "attribute_id"),
        Index("ix_product_attribute_values_order", "attribute_id", "sort_order"),
    )

    attribute_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_attributes.id", ondelete="RESTRICT"), nullable=False
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class ProductVariantAttributeValueModel(
    UuidPrimaryKeyMixin, TimestampMixin, VersionNumberMixin, Base
):
    __tablename__ = "product_variant_attribute_values"
    __table_args__ = (
        UniqueConstraint(
            "variant_id",
            "attribute_value_id",
            name="uq_product_variant_attribute_values_variant_value",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index(
            "ix_product_variant_attribute_values_variant",
            "variant_id",
        ),
        Index(
            "ix_product_variant_attribute_values_value",
            "attribute_value_id",
        ),
    )

    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    attribute_value_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_attribute_values.id", ondelete="RESTRICT"),
        nullable=False,
    )


class EventOutboxModel(UuidPrimaryKeyMixin, VersionNumberMixin, Base):
    __tablename__ = "event_outbox"
    __table_args__ = (
        CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_event_outbox_status", "status"),
        Index("ix_event_outbox_occurred_at", "occurred_at"),
        Index("ix_event_outbox_aggregate_type", "aggregate_type"),
        Index("ix_event_outbox_available", "status", "available_at"),
        Index("ix_event_outbox_stale_lock", "status", "locked_at"),
    )

    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    event_name: Mapped[str] = mapped_column(String(150), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(
            OutboxStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=OutboxStatus.PENDING,
        server_default=OutboxStatus.PENDING.value,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
