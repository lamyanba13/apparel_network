"""create orders

Revision ID: 7e9f1a3b5d68
Revises: 6d8e0f2a4c57
Create Date: 2026-08-04 14:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "7e9f1a3b5d68"
down_revision: str | Sequence[str] | None = "6d8e0f2a4c57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "order:create": UUID("22000000-0000-7000-8000-000000000033"),
    "order:view": UUID("22000000-0000-7000-8000-000000000034"),
    "order:update": UUID("22000000-0000-7000-8000-000000000035"),
    "order:confirm": UUID("22000000-0000-7000-8000-000000000036"),
}
ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "admin": UUID("21000000-0000-7000-8000-000000000002"),
    "store_owner": UUID("21000000-0000-7000-8000-000000000003"),
    "store_staff": UUID("21000000-0000-7000-8000-000000000004"),
    "customer": UUID("21000000-0000-7000-8000-000000000005"),
}


def upgrade() -> None:
    op.execute(
        sa.schema.CreateSequence(
            sa.Sequence("order_number_sequence", start=1, maxvalue=999_999)
        )
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("checkout_session_id", sa.Uuid(), nullable=False),
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("order_number", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "confirmed", "cancelled", native_enum=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "order_number ~ '^ORD-[0-9]{8}-[0-9]{6}$'",
            name="order_number_format",
        ),
        sa.CheckConstraint("char_length(currency) = 3", name="currency_length"),
        sa.CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        sa.CheckConstraint("subtotal >= 0", name="subtotal_nonnegative"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "(status = 'pending' AND confirmed_at IS NULL "
            "AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'confirmed' AND confirmed_at IS NOT NULL "
            "AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'cancelled' AND confirmed_at IS NOT NULL "
            "AND cancelled_at IS NOT NULL AND deleted_at IS NOT NULL)",
            name="lifecycle_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["checkout_session_id"], ["checkout_sessions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["cart_id"], ["shopping_carts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number", name="uq_orders_order_number"),
        sa.UniqueConstraint("checkout_session_id", name="uq_orders_checkout_session"),
    )
    for name, columns in (
        ("ix_orders_customer", ["customer_id"]),
        ("ix_orders_store", ["store_id"]),
        ("ix_orders_status", ["status"]),
        ("ix_orders_placed_at", ["placed_at"]),
    ):
        op.create_index(name, "orders", columns)

    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price_id", sa.Uuid(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("inventory_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"),
        sa.CheckConstraint("char_length(currency) = 3", name="currency_length"),
        sa.CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        sa.CheckConstraint("inventory_version >= 1", name="inventory_version_positive"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["product_variants.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["price_id"], ["product_prices.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["inventory_id"], ["inventory_items.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id", "variant_id", name="uq_order_items_order_variant"
        ),
    )
    for name, columns in (
        ("ix_order_items_order", ["order_id"]),
        ("ix_order_items_product", ["product_id"]),
        ("ix_order_items_variant", ["variant_id"]),
        ("ix_order_items_price", ["price_id"]),
        ("ix_order_items_inventory", ["inventory_id"]),
    ):
        op.create_index(name, "order_items", columns)
    _seed_permissions()


def downgrade() -> None:
    _remove_permissions()
    for name in (
        "ix_order_items_inventory",
        "ix_order_items_price",
        "ix_order_items_variant",
        "ix_order_items_product",
        "ix_order_items_order",
    ):
        op.drop_index(name, table_name="order_items")
    op.drop_table("order_items")
    for name in (
        "ix_orders_placed_at",
        "ix_orders_status",
        "ix_orders_store",
        "ix_orders_customer",
    ):
        op.drop_index(name, table_name="orders")
    op.drop_table("orders")
    op.execute(sa.schema.DropSequence(sa.Sequence("order_number_sequence")))


def _seed_permissions() -> None:
    permissions = sa.table(
        "identity_permissions",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("resource", sa.String()),
        sa.column("action", sa.String()),
    )
    role_permissions = sa.table(
        "identity_role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
    )
    op.bulk_insert(
        permissions,
        [
            {
                "id": permission_id,
                "name": name,
                "description": f"Order permission for {name}.",
                "resource": "order",
                "action": name.split(":", maxsplit=1)[1],
            }
            for name, permission_id in PERMISSIONS.items()
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_id, "permission_id": permission_id}
            for role_id in ROLE_IDS.values()
            for permission_id in PERMISSIONS.values()
        ],
    )


def _remove_permissions() -> None:
    bind = op.get_bind()
    ids = tuple(PERMISSIONS.values())
    role_permissions = sa.table(
        "identity_role_permissions", sa.column("permission_id", sa.Uuid())
    )
    permissions = sa.table("identity_permissions", sa.column("id", sa.Uuid()))
    bind.execute(
        sa.delete(role_permissions).where(role_permissions.c.permission_id.in_(ids))
    )
    bind.execute(sa.delete(permissions).where(permissions.c.id.in_(ids)))
