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
from app.modules.cart.domain import CartStatus
from app.modules.pricing.domain import CustomerGroup


class ShoppingCartModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "shopping_carts"
    __table_args__ = (
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        CheckConstraint("expires_at > created_at", name="expiration_after_creation"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "checked_out_at IS NULL OR status = 'checked_out'",
            name="checkout_timestamp_status",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR status = 'abandoned'",
            name="deleted_abandoned",
        ),
        Index(
            "uq_shopping_carts_active_user_store",
            "user_id",
            "store_id",
            unique=True,
            postgresql_where=text("status = 'active' AND deleted_at IS NULL"),
        ),
        Index("ix_shopping_carts_user", "user_id"),
        Index("ix_shopping_carts_store", "store_id"),
        Index("ix_shopping_carts_status", "status"),
        Index("ix_shopping_carts_expires_at", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[CartStatus] = mapped_column(
        Enum(
            CartStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=CartStatus.ACTIVE,
        server_default=CartStatus.ACTIVE.value,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
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
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    checked_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class ShoppingCartItemModel(
    UuidPrimaryKeyMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "shopping_cart_items"
    __table_args__ = (
        Index(
            "uq_shopping_cart_items_cart_variant",
            "cart_id",
            "variant_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"),
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_shopping_cart_items_cart", "cart_id"),
        Index("ix_shopping_cart_items_product", "product_id"),
        Index("ix_shopping_cart_items_variant", "variant_id"),
        Index("ix_shopping_cart_items_price", "price_snapshot_id"),
    )

    cart_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopping_carts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    price_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_prices.id", ondelete="RESTRICT"), nullable=False
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    inventory_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)
