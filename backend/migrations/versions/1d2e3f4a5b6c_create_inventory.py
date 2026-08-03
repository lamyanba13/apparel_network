"""create inventory"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1d2e3f4a5b6c"
down_revision: str | Sequence[str] | None = "697a9e0d3c1b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("inventory_items", sa.Column("id", sa.Uuid(), nullable=False), sa.Column("variant_id", sa.Uuid(), nullable=False), sa.Column("product_id", sa.Uuid(), nullable=False), sa.Column("catalog_id", sa.Uuid(), nullable=False), sa.Column("store_id", sa.Uuid(), nullable=False), sa.Column("sku_snapshot", sa.String(64), nullable=False), sa.Column("quantity_on_hand", sa.Integer(), server_default="0", nullable=False), sa.Column("quantity_reserved", sa.Integer(), server_default="0", nullable=False), sa.Column("quantity_available", sa.Integer(), server_default="0", nullable=False), sa.Column("status", sa.Enum("active", "out_of_stock", "discontinued", native_enum=False), server_default="active", nullable=False), sa.Column("tracking_policy", sa.Enum("track", "do_not_track", "preorder", native_enum=False), server_default="track", nullable=False), sa.Column("low_stock_threshold", sa.Integer(), server_default="0", nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("deleted_at", sa.DateTime(timezone=True)), sa.Column("version", sa.Integer(), server_default="1", nullable=False), sa.Column("created_by_id", sa.Uuid()), sa.Column("updated_by_id", sa.Uuid()), sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["catalog_id"], ["catalogs.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("variant_id", name="uq_inventory_items_variant"), sa.CheckConstraint("quantity_on_hand >= 0", name="inventory_on_hand_nonnegative"), sa.CheckConstraint("quantity_reserved >= 0", name="inventory_reserved_nonnegative"), sa.CheckConstraint("quantity_available >= 0", name="inventory_available_nonnegative"), sa.CheckConstraint("quantity_available = quantity_on_hand - quantity_reserved", name="inventory_available_derived"), sa.CheckConstraint("low_stock_threshold >= 0", name="inventory_threshold_nonnegative"), sa.CheckConstraint("version >= 1", name="inventory_version_positive"))
    for name, columns in (("ix_inventory_items_product", ["product_id"]), ("ix_inventory_items_catalog", ["catalog_id"]), ("ix_inventory_items_store", ["store_id"]), ("ix_inventory_items_status", ["status"]), ("ix_inventory_items_available", ["quantity_available"]), ("ix_inventory_items_deleted", ["deleted_at"])):
        op.create_index(name, "inventory_items", columns)


def downgrade() -> None:
    for name in ("ix_inventory_items_deleted", "ix_inventory_items_available", "ix_inventory_items_status", "ix_inventory_items_store", "ix_inventory_items_catalog", "ix_inventory_items_product"):
        op.drop_index(name, table_name="inventory_items")
    op.drop_table("inventory_items")
