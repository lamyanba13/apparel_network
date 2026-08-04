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
    Sequence,
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
from app.modules.orders.domain import OrderStatus

ORDER_NUMBER_SEQUENCE = Sequence("order_number_sequence")


class OrderModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("order_number", name="uq_orders_order_number"),
        UniqueConstraint("checkout_session_id", name="uq_orders_checkout_session"),
        CheckConstraint(
            "order_number ~ '^ORD-[0-9]{8}-[0-9]{6}$'",
            name="order_number_format",
        ),
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        CheckConstraint("subtotal >= 0", name="subtotal_nonnegative"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(status = 'pending' AND confirmed_at IS NULL "
            "AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'confirmed' AND confirmed_at IS NOT NULL "
            "AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'cancelled' AND confirmed_at IS NOT NULL "
            "AND cancelled_at IS NOT NULL AND deleted_at IS NOT NULL)",
            name="lifecycle_timestamps",
        ),
        Index("ix_orders_customer", "customer_id"),
        Index("ix_orders_store", "store_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_placed_at", "placed_at"),
    )

    checkout_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("checkout_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    cart_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopping_carts.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    order_number: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(
            OrderStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=OrderStatus.PENDING,
        server_default=OrderStatus.PENDING.value,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class OrderItemModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "variant_id", name="uq_order_items_order_variant"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"),
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        CheckConstraint("inventory_version >= 1", name="inventory_version_positive"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_order_items_order", "order_id"),
        Index("ix_order_items_product", "product_id"),
        Index("ix_order_items_variant", "variant_id"),
        Index("ix_order_items_price", "price_id"),
        Index("ix_order_items_inventory", "inventory_id"),
    )

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
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
    snapshot_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
