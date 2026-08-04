from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
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
from app.modules.reservations.domain import ReservationStatus


class InventoryReservationModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(status IN ('created', 'active') AND released_at IS NULL "
            "AND consumed_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'consumed' AND released_at IS NULL "
            "AND consumed_at IS NOT NULL AND deleted_at IS NULL) OR "
            "(status = 'released' AND released_at IS NOT NULL "
            "AND consumed_at IS NULL AND deleted_at IS NOT NULL) OR "
            "(status = 'expired' AND released_at IS NULL "
            "AND consumed_at IS NULL AND deleted_at IS NOT NULL)",
            name="lifecycle_timestamps",
        ),
        Index(
            "uq_inventory_reservations_active_order",
            "order_id",
            unique=True,
            postgresql_where=text("status = 'active' AND deleted_at IS NULL"),
        ),
        Index("ix_inventory_reservations_payment", "payment_id"),
        Index("ix_inventory_reservations_customer", "customer_id"),
        Index("ix_inventory_reservations_store", "store_id"),
        Index("ix_inventory_reservations_status", "status"),
        Index("ix_inventory_reservations_expires_at", "expires_at"),
    )

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    payment_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_intents.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(
            ReservationStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=ReservationStatus.CREATED,
        server_default=ReservationStatus.CREATED.value,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class InventoryReservationItemModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "inventory_reservation_items"
    __table_args__ = (
        UniqueConstraint(
            "reservation_id",
            "inventory_item_id",
            name="uq_inventory_reservation_items_inventory",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("inventory_version >= 1", name="inventory_version_positive"),
        Index("ix_inventory_reservation_items_reservation", "reservation_id"),
        Index("ix_inventory_reservation_items_inventory", "inventory_item_id"),
        Index("ix_inventory_reservation_items_variant", "variant_id"),
    )

    reservation_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_reservations.id", ondelete="CASCADE"), nullable=False
    )
    inventory_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False
    )
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    inventory_version: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
