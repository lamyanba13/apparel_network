"""create inventory reservations

Revision ID: 9a1b3c5d7e80
Revises: 8f0a2b4c6d79
Create Date: 2026-08-04 18:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "9a1b3c5d7e80"
down_revision: str | Sequence[str] | None = "8f0a2b4c6d79"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "reservation:view": UUID("22000000-0000-7000-8000-000000000042"),
    "reservation:update": UUID("22000000-0000-7000-8000-000000000043"),
    "reservation:consume": UUID("22000000-0000-7000-8000-000000000044"),
    "reservation:release": UUID("22000000-0000-7000-8000-000000000045"),
}
RESERVATION_CREATE_ID = UUID("22000000-0000-7000-8000-000000000010")
ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "admin": UUID("21000000-0000-7000-8000-000000000002"),
    "store_owner": UUID("21000000-0000-7000-8000-000000000003"),
    "store_staff": UUID("21000000-0000-7000-8000-000000000004"),
    "customer": UUID("21000000-0000-7000-8000-000000000005"),
}
CREATE_GRANT_ROLES = ("admin", "store_owner", "store_staff")


def upgrade() -> None:
    op.create_table(
        "inventory_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "created",
                "active",
                "consumed",
                "released",
                "expired",
                native_enum=False,
            ),
            server_default="created",
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
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
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payment_intents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_inventory_reservations_active_order",
        "inventory_reservations",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND deleted_at IS NULL"),
    )
    for name, columns in (
        ("ix_inventory_reservations_payment", ["payment_id"]),
        ("ix_inventory_reservations_customer", ["customer_id"]),
        ("ix_inventory_reservations_store", ["store_id"]),
        ("ix_inventory_reservations_status", ["status"]),
        ("ix_inventory_reservations_expires_at", ["expires_at"]),
    ):
        op.create_index(name, "inventory_reservations", columns)

    op.create_table(
        "inventory_reservation_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reservation_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_item_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("inventory_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("inventory_version >= 1", name="inventory_version_positive"),
        sa.ForeignKeyConstraint(
            ["reservation_id"], ["inventory_reservations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"], ["inventory_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["product_variants.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "reservation_id",
            "inventory_item_id",
            name="uq_inventory_reservation_items_inventory",
        ),
    )
    for name, columns in (
        ("ix_inventory_reservation_items_reservation", ["reservation_id"]),
        ("ix_inventory_reservation_items_inventory", ["inventory_item_id"]),
        ("ix_inventory_reservation_items_variant", ["variant_id"]),
    ):
        op.create_index(name, "inventory_reservation_items", columns)
    _seed_permissions()


def downgrade() -> None:
    _remove_permissions()
    for name in (
        "ix_inventory_reservation_items_variant",
        "ix_inventory_reservation_items_inventory",
        "ix_inventory_reservation_items_reservation",
    ):
        op.drop_index(name, table_name="inventory_reservation_items")
    op.drop_table("inventory_reservation_items")
    for name in (
        "ix_inventory_reservations_expires_at",
        "ix_inventory_reservations_status",
        "ix_inventory_reservations_store",
        "ix_inventory_reservations_customer",
        "ix_inventory_reservations_payment",
        "uq_inventory_reservations_active_order",
    ):
        op.drop_index(name, table_name="inventory_reservations")
    op.drop_table("inventory_reservations")


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
                "description": f"Reservation permission for {name}.",
                "resource": "reservation",
                "action": name.split(":", maxsplit=1)[1],
            }
            for name, permission_id in PERMISSIONS.items()
        ],
    )
    grants = [
        {"role_id": role_id, "permission_id": permission_id}
        for role_id in ROLE_IDS.values()
        for permission_id in PERMISSIONS.values()
    ]
    grants.extend(
        {
            "role_id": ROLE_IDS[role_name],
            "permission_id": RESERVATION_CREATE_ID,
        }
        for role_name in CREATE_GRANT_ROLES
    )
    op.bulk_insert(role_permissions, grants)


def _remove_permissions() -> None:
    bind = op.get_bind()
    new_ids = tuple(PERMISSIONS.values())
    added_create_roles = tuple(ROLE_IDS[name] for name in CREATE_GRANT_ROLES)
    role_permissions = sa.table(
        "identity_role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
    )
    permissions = sa.table("identity_permissions", sa.column("id", sa.Uuid()))
    bind.execute(
        sa.delete(role_permissions).where(role_permissions.c.permission_id.in_(new_ids))
    )
    bind.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id == RESERVATION_CREATE_ID,
            role_permissions.c.role_id.in_(added_create_roles),
        )
    )
    bind.execute(sa.delete(permissions).where(permissions.c.id.in_(new_ids)))
