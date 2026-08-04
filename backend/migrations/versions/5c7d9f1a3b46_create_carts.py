"""create carts

Revision ID: 5c7d9f1a3b46
Revises: 4b6c8e0a2d35
Create Date: 2026-08-04 12:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "5c7d9f1a3b46"
down_revision: str | Sequence[str] | None = "4b6c8e0a2d35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "cart:create": UUID("22000000-0000-7000-8000-000000000025"),
    "cart:view": UUID("22000000-0000-7000-8000-000000000026"),
    "cart:update": UUID("22000000-0000-7000-8000-000000000027"),
    "cart:delete": UUID("22000000-0000-7000-8000-000000000028"),
}
ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "admin": UUID("21000000-0000-7000-8000-000000000002"),
    "store_owner": UUID("21000000-0000-7000-8000-000000000003"),
    "store_staff": UUID("21000000-0000-7000-8000-000000000004"),
    "customer": UUID("21000000-0000-7000-8000-000000000005"),
}


def upgrade() -> None:
    op.create_table(
        "shopping_carts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "checked_out", "abandoned", "expired", native_enum=False),
            server_default="active",
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "customer_group",
            sa.Enum("public", "wholesale", "vip", "staff", "custom", native_enum=False),
            server_default="public",
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("char_length(currency) = 3", name="currency_length"),
        sa.CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        sa.CheckConstraint("expires_at > created_at", name="expiration_after_creation"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "checked_out_at IS NULL OR status = 'checked_out'",
            name="checkout_timestamp_status",
        ),
        sa.CheckConstraint(
            "deleted_at IS NULL OR status = 'abandoned'", name="deleted_abandoned"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_shopping_carts_user", ["user_id"]),
        ("ix_shopping_carts_store", ["store_id"]),
        ("ix_shopping_carts_status", ["status"]),
        ("ix_shopping_carts_expires_at", ["expires_at"]),
    ):
        op.create_index(name, "shopping_carts", columns)
    op.create_index(
        "uq_shopping_carts_active_user_store",
        "shopping_carts",
        ["user_id", "store_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND deleted_at IS NULL"),
    )

    op.create_table(
        "shopping_cart_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("inventory_snapshot", JSONB(), nullable=False),
        sa.Column(
            "added_at",
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"),
        sa.CheckConstraint("char_length(currency) = 3", name="currency_length"),
        sa.CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(["cart_id"], ["shopping_carts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["product_variants.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["price_snapshot_id"], ["product_prices.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_shopping_cart_items_cart", ["cart_id"]),
        ("ix_shopping_cart_items_product", ["product_id"]),
        ("ix_shopping_cart_items_variant", ["variant_id"]),
        ("ix_shopping_cart_items_price", ["price_snapshot_id"]),
    ):
        op.create_index(name, "shopping_cart_items", columns)
    op.create_index(
        "uq_shopping_cart_items_cart_variant",
        "shopping_cart_items",
        ["cart_id", "variant_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    _seed_permissions()


def downgrade() -> None:
    _remove_permissions()
    for name in (
        "uq_shopping_cart_items_cart_variant",
        "ix_shopping_cart_items_price",
        "ix_shopping_cart_items_variant",
        "ix_shopping_cart_items_product",
        "ix_shopping_cart_items_cart",
    ):
        op.drop_index(name, table_name="shopping_cart_items")
    op.drop_table("shopping_cart_items")
    for name in (
        "uq_shopping_carts_active_user_store",
        "ix_shopping_carts_expires_at",
        "ix_shopping_carts_status",
        "ix_shopping_carts_store",
        "ix_shopping_carts_user",
    ):
        op.drop_index(name, table_name="shopping_carts")
    op.drop_table("shopping_carts")


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
                "description": f"Shopping Cart permission for {name}.",
                "resource": "cart",
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
