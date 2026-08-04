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
    func,
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
from app.modules.shipments.domain import ShipmentStatus


class ShipmentModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_shipments_order"),
        UniqueConstraint("reservation_id", name="uq_shipments_reservation"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(status NOT IN ('shipped', 'out_for_delivery', 'delivered', "
            "'return_requested', 'returned') OR shipped_at IS NOT NULL)",
            name="shipped_timestamp",
        ),
        CheckConstraint(
            "(status != 'delivered' OR delivered_at IS NOT NULL)",
            name="delivered_timestamp",
        ),
        CheckConstraint(
            "(status != 'cancelled' OR deleted_at IS NOT NULL)",
            name="cancelled_archive",
        ),
        Index("ix_shipments_payment", "payment_id"),
        Index("ix_shipments_customer", "customer_id"),
        Index("ix_shipments_store", "store_id"),
        Index("ix_shipments_status", "status"),
    )

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    reservation_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_reservations.id", ondelete="RESTRICT"), nullable=False
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
    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(
            ShipmentStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=ShipmentStatus.CREATED,
        server_default=ShipmentStatus.CREATED.value,
    )
    carrier: Mapped[str | None] = mapped_column(String(100))
    tracking_number: Mapped[str | None] = mapped_column(String(255))
    tracking_url: Mapped[str | None] = mapped_column(String(2048))
    shipping_method: Mapped[str] = mapped_column(String(100), nullable=False)
    estimated_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class ShipmentPackageModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "shipment_packages"
    __table_args__ = (
        UniqueConstraint(
            "shipment_id", "package_number", name="uq_shipment_packages_number"
        ),
        CheckConstraint("weight > 0", name="weight_positive"),
        CheckConstraint(
            "length > 0 AND width > 0 AND height > 0", name="dimensions_positive"
        ),
        Index("ix_shipment_packages_shipment", "shipment_id"),
    )

    shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False
    )
    package_number: Mapped[str] = mapped_column(String(100), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    length: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    width: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    height: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    label_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ShipmentTrackingEventModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "shipment_tracking_events"
    __table_args__ = (
        Index("ix_shipment_tracking_events_shipment", "shipment_id"),
        Index("ix_shipment_tracking_events_occurred_at", "occurred_at"),
    )

    shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(
            ShipmentStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    location: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
