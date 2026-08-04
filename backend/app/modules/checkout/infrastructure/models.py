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
from app.modules.checkout.domain import CheckoutStatus


class CheckoutSessionModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "checkout_sessions"
    __table_args__ = (
        UniqueConstraint("cart_id", name="uq_checkout_sessions_cart"),
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        CheckConstraint("subtotal >= 0", name="subtotal_nonnegative"),
        CheckConstraint("expires_at > created_at", name="expiration_after_creation"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "completed_at IS NULL OR status = 'confirmed'",
            name="completion_timestamp_status",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR status = 'cancelled'",
            name="deleted_cancelled",
        ),
        Index("ix_checkout_sessions_user", "user_id"),
        Index("ix_checkout_sessions_store", "store_id"),
        Index("ix_checkout_sessions_status", "status"),
        Index("ix_checkout_sessions_expires_at", "expires_at"),
    )

    cart_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopping_carts.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[CheckoutStatus] = mapped_column(
        Enum(
            CheckoutStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=CheckoutStatus.ACTIVE,
        server_default=CheckoutStatus.ACTIVE.value,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class CheckoutSessionItemModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "checkout_session_items"
    __table_args__ = (
        UniqueConstraint(
            "checkout_session_id",
            "variant_id",
            name="uq_checkout_session_items_session_variant",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"),
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        CheckConstraint("inventory_version >= 1", name="inventory_version_positive"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_checkout_session_items_session", "checkout_session_id"),
        Index("ix_checkout_session_items_product", "product_id"),
        Index("ix_checkout_session_items_variant", "variant_id"),
        Index("ix_checkout_session_items_price", "price_id"),
        Index("ix_checkout_session_items_inventory", "inventory_id"),
    )

    checkout_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("checkout_sessions.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    price_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_prices.id", ondelete="RESTRICT"), nullable=False
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    inventory_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False
    )
    inventory_version: Mapped[int] = mapped_column(nullable=False)
    price_snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    inventory_snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
