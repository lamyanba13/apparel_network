from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
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
from app.modules.pricing.domain import CustomerGroup, PriceListStatus, PriceStatus


class ProductPriceModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "product_prices"
    __table_args__ = (
        CheckConstraint("base_price >= 0", name="base_nonnegative"),
        CheckConstraint("sale_price >= 0", name="sale_nonnegative"),
        CheckConstraint("compare_at_price >= 0", name="compare_nonnegative"),
        CheckConstraint("cost_price >= 0", name="cost_nonnegative"),
        CheckConstraint(
            "sale_price IS NULL OR sale_price <= base_price",
            name="sale_not_above_base",
        ),
        CheckConstraint(
            "compare_at_price IS NULL OR compare_at_price >= base_price",
            name="compare_not_below_base",
        ),
        CheckConstraint(
            "effective_from IS NULL OR effective_until IS NULL "
            "OR effective_from < effective_until",
            name="effective_period",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'",
            name="deleted_archived",
        ),
        Index("ix_product_prices_store", "store_id"),
        Index("ix_product_prices_product", "product_id"),
        Index("ix_product_prices_variant", "variant_id"),
        Index("ix_product_prices_status", "status"),
        Index("ix_product_prices_currency", "currency_code"),
        Index("ix_product_prices_effective_from", "effective_from"),
        Index("ix_product_prices_effective_until", "effective_until"),
        Index(
            "uq_product_prices_active_variant_currency_period",
            "variant_id",
            "currency_code",
            "effective_from",
            "effective_until",
            unique=True,
            postgresql_where=text(
                "status = 'active' AND variant_id IS NOT NULL AND deleted_at IS NULL"
            ),
            postgresql_nulls_not_distinct=True,
        ),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    variant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=True
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    base_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    compare_at_price: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 4), nullable=True
    )
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    tax_class: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[PriceStatus] = mapped_column(
        Enum(
            PriceStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=PriceStatus.DRAFT,
        server_default=PriceStatus.DRAFT.value,
    )
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class PriceListModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "price_lists"
    __table_args__ = (
        UniqueConstraint("store_id", "slug", name="uq_price_lists_store_slug"),
        CheckConstraint("priority >= 0", name="priority_nonnegative"),
        CheckConstraint(
            "effective_from IS NULL OR effective_until IS NULL "
            "OR effective_from < effective_until",
            name="effective_period",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'",
            name="deleted_archived",
        ),
        CheckConstraint(
            "is_default = false OR status = 'active'",
            name="default_active",
        ),
        CheckConstraint(
            "is_default = false OR customer_group = 'public'",
            name="default_public",
        ),
        Index("ix_price_lists_store", "store_id"),
        Index("ix_price_lists_currency", "currency_code"),
        Index("ix_price_lists_priority", "priority"),
        Index("ix_price_lists_status", "status"),
        Index("ix_price_lists_effective_from", "effective_from"),
        Index("ix_price_lists_effective_until", "effective_until"),
        Index(
            "uq_price_lists_default_store_currency",
            "store_id",
            "currency_code",
            unique=True,
            postgresql_where=text("is_default = true AND deleted_at IS NULL"),
        ),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[PriceListStatus] = mapped_column(
        Enum(
            PriceListStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=PriceListStatus.DRAFT,
        server_default=PriceListStatus.DRAFT.value,
    )
    customer_group: Mapped[CustomerGroup] = mapped_column(
        Enum(
            CustomerGroup,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=CustomerGroup.PUBLIC,
        server_default=CustomerGroup.PUBLIC.value,
    )
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_default: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class PriceListAssignmentModel(UuidPrimaryKeyMixin, VersionNumberMixin, Base):
    __tablename__ = "price_list_assignments"
    __table_args__ = (
        UniqueConstraint(
            "price_list_id",
            "price_id",
            name="uq_price_list_assignments_price_list_price",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_price_list_assignments_price_list", "price_list_id"),
        Index("ix_price_list_assignments_price", "price_id"),
    )

    price_list_id: Mapped[UUID] = mapped_column(
        ForeignKey("price_lists.id", ondelete="CASCADE"), nullable=False
    )
    price_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_prices.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by_id: Mapped[UUID | None] = mapped_column(nullable=True)
