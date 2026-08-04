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
from app.modules.returns.domain import (
    InventoryDisposition,
    RefundStatus,
    RefundTransactionType,
    ReturnStatus,
)


class ReturnModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "returns"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(status != 'approved' OR approved_at IS NOT NULL) AND "
            "(status NOT IN ('received', 'inspected', 'refund_pending', 'refunded') "
            "OR received_at IS NOT NULL) AND "
            "(status NOT IN ('inspected', 'refund_pending', 'refunded') "
            "OR inspected_at IS NOT NULL) AND "
            "(status != 'rejected' OR rejected_at IS NOT NULL) AND "
            "(status != 'cancelled' OR cancelled_at IS NOT NULL)",
            name="lifecycle_timestamps",
        ),
        Index("ix_returns_order", "order_id"),
        Index("ix_returns_shipment", "shipment_id"),
        Index("ix_returns_payment", "payment_id"),
        Index("ix_returns_customer", "customer_id"),
        Index("ix_returns_store", "store_id"),
        Index("ix_returns_status", "status"),
    )

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("shipments.id", ondelete="RESTRICT"), nullable=False
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
    status: Mapped[ReturnStatus] = mapped_column(
        Enum(
            ReturnStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=ReturnStatus.REQUESTED,
        server_default=ReturnStatus.REQUESTED.value,
    )
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class ReturnItemModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "return_items"
    __table_args__ = (
        UniqueConstraint(
            "return_id", "order_item_id", name="uq_return_items_order_item"
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        Index("ix_return_items_return", "return_id"),
        Index("ix_return_items_order_item", "order_item_id"),
        Index("ix_return_items_inventory", "inventory_item_id"),
    )

    return_id: Mapped[UUID] = mapped_column(
        ForeignKey("returns.id", ondelete="CASCADE"), nullable=False
    )
    order_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("order_items.id", ondelete="RESTRICT"), nullable=False
    )
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    inventory_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    disposition: Mapped[InventoryDisposition] = mapped_column(
        Enum(
            InventoryDisposition,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=InventoryDisposition.INSPECTION_REQUIRED,
        server_default=InventoryDisposition.INSPECTION_REQUIRED.value,
    )
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RefundModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "refunds"
    __table_args__ = (
        UniqueConstraint("return_id", name="uq_refunds_return"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(status != 'completed' OR completed_at IS NOT NULL) AND "
            "(status != 'failed' OR failed_at IS NOT NULL)",
            name="lifecycle_timestamps",
        ),
        Index("ix_refunds_payment", "payment_id"),
        Index("ix_refunds_customer", "customer_id"),
        Index("ix_refunds_store", "store_id"),
        Index("ix_refunds_status", "status"),
    )

    return_id: Mapped[UUID] = mapped_column(
        ForeignKey("returns.id", ondelete="RESTRICT"), nullable=False
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
    status: Mapped[RefundStatus] = mapped_column(
        Enum(
            RefundStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=RefundStatus.PENDING,
        server_default=RefundStatus.PENDING.value,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(255))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_id: Mapped[UUID | None] = mapped_column(nullable=True)


class RefundTransactionModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "refund_transactions"
    __table_args__ = (
        UniqueConstraint(
            "provider_transaction_id", name="uq_refund_transactions_provider_id"
        ),
        Index("ix_refund_transactions_refund", "refund_id"),
        Index("ix_refund_transactions_occurred_at", "occurred_at"),
    )

    refund_id: Mapped[UUID] = mapped_column(
        ForeignKey("refunds.id", ondelete="CASCADE"), nullable=False
    )
    provider_transaction_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[RefundTransactionType] = mapped_column(
        Enum(
            RefundTransactionType,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    status: Mapped[RefundStatus] = mapped_column(
        Enum(
            RefundStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    provider_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
