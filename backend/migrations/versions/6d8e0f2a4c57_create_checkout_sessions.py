"""create checkout sessions

Revision ID: 6d8e0f2a4c57
Revises: 5c7d9f1a3b46
Create Date: 2026-08-04 13:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "6d8e0f2a4c57"
down_revision: str | Sequence[str] | None = "5c7d9f1a3b46"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "checkout:create": UUID("22000000-0000-7000-8000-000000000029"),
    "checkout:view": UUID("22000000-0000-7000-8000-000000000030"),
    "checkout:update": UUID("22000000-0000-7000-8000-000000000031"),
    "checkout:confirm": UUID("22000000-0000-7000-8000-000000000032"),
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
        "checkout_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "confirmed", "expired", "cancelled", native_enum=False),
            server_default="active",
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("subtotal >= 0", name="subtotal_nonnegative"),
        sa.CheckConstraint("expires_at > created_at", name="expiration_after_creation"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "completed_at IS NULL OR status = 'confirmed'",
            name="completion_timestamp_status",
        ),
        sa.CheckConstraint(
            "deleted_at IS NULL OR status = 'cancelled'", name="deleted_cancelled"
        ),
        sa.ForeignKeyConstraint(
            ["cart_id"], ["shopping_carts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cart_id", name="uq_checkout_sessions_cart"),
    )
    for name, columns in (
        ("ix_checkout_sessions_user", ["user_id"]),
        ("ix_checkout_sessions_store", ["store_id"]),
        ("ix_checkout_sessions_status", ["status"]),
        ("ix_checkout_sessions_expires_at", ["expires_at"]),
    ):
        op.create_index(name, "checkout_sessions", columns)

    op.create_table(
        "checkout_session_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("checkout_session_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price_id", sa.Uuid(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("inventory_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_version", sa.Integer(), nullable=False),
        sa.Column("price_snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "inventory_snapshot_time", sa.DateTime(timezone=True), nullable=False
        ),
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
        sa.ForeignKeyConstraint(
            ["checkout_session_id"], ["checkout_sessions.id"], ondelete="CASCADE"
        ),
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
            "checkout_session_id",
            "variant_id",
            name="uq_checkout_session_items_session_variant",
        ),
    )
    for name, columns in (
        ("ix_checkout_session_items_session", ["checkout_session_id"]),
        ("ix_checkout_session_items_product", ["product_id"]),
        ("ix_checkout_session_items_variant", ["variant_id"]),
        ("ix_checkout_session_items_price", ["price_id"]),
        ("ix_checkout_session_items_inventory", ["inventory_id"]),
    ):
        op.create_index(name, "checkout_session_items", columns)
    _seed_permissions()


def downgrade() -> None:
    _remove_permissions()
    for name in (
        "ix_checkout_session_items_inventory",
        "ix_checkout_session_items_price",
        "ix_checkout_session_items_variant",
        "ix_checkout_session_items_product",
        "ix_checkout_session_items_session",
    ):
        op.drop_index(name, table_name="checkout_session_items")
    op.drop_table("checkout_session_items")
    for name in (
        "ix_checkout_sessions_expires_at",
        "ix_checkout_sessions_status",
        "ix_checkout_sessions_store",
        "ix_checkout_sessions_user",
    ):
        op.drop_index(name, table_name="checkout_sessions")
    op.drop_table("checkout_sessions")


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
                "description": f"Checkout permission for {name}.",
                "resource": "checkout",
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
