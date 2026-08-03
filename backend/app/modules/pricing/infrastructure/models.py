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
    Numeric,
    String,
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
from app.modules.pricing.domain import PriceStatus


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
