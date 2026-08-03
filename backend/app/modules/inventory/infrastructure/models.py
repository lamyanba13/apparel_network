from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
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
from app.modules.inventory.domain import InventoryStatus, TrackingPolicy


class InventoryItemModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    VersionNumberMixin,
    AuditFieldsMixin,
    Base,
):
    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint("quantity_on_hand >= 0", name="inventory_on_hand_nonnegative"),
        CheckConstraint(
            "quantity_reserved >= 0", name="inventory_reserved_nonnegative"
        ),
        CheckConstraint(
            "quantity_available >= 0", name="inventory_available_nonnegative"
        ),
        CheckConstraint(
            "quantity_available = quantity_on_hand - quantity_reserved",
            name="inventory_available_derived",
        ),
        CheckConstraint(
            "low_stock_threshold >= 0", name="inventory_threshold_nonnegative"
        ),
        CheckConstraint("version >= 1", name="inventory_version_positive"),
        UniqueConstraint("variant_id", name="uq_inventory_items_variant"),
        Index("ix_inventory_items_product", "product_id"),
        Index("ix_inventory_items_catalog", "catalog_id"),
        Index("ix_inventory_items_store", "store_id"),
        Index("ix_inventory_items_status", "status"),
        Index("ix_inventory_items_available", "quantity_available"),
        Index("ix_inventory_items_deleted", "deleted_at"),
    )
    variant_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    catalog_id: Mapped[UUID] = mapped_column(
        ForeignKey("catalogs.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    sku_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity_on_hand: Mapped[int] = mapped_column(nullable=False, server_default="0")
    quantity_reserved: Mapped[int] = mapped_column(nullable=False, server_default="0")
    quantity_available: Mapped[int] = mapped_column(nullable=False, server_default="0")
    status: Mapped[InventoryStatus] = mapped_column(
        Enum(
            InventoryStatus,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=InventoryStatus.ACTIVE,
        server_default=InventoryStatus.ACTIVE.value,
    )
    tracking_policy: Mapped[TrackingPolicy] = mapped_column(
        Enum(
            TrackingPolicy,
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=TrackingPolicy.TRACK,
        server_default=TrackingPolicy.TRACK.value,
    )
    low_stock_threshold: Mapped[int] = mapped_column(nullable=False, server_default="0")
