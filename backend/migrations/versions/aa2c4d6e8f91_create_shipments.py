"""create shipments

Revision ID: aa2c4d6e8f91
Revises: 9a1b3c5d7e80
Create Date: 2026-08-04 20:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "aa2c4d6e8f91"
down_revision: str | Sequence[str] | None = "9a1b3c5d7e80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "shipment:create": UUID("22000000-0000-7000-8000-000000000046"),
    "shipment:view": UUID("22000000-0000-7000-8000-000000000047"),
    "shipment:update": UUID("22000000-0000-7000-8000-000000000048"),
    "shipment:ship": UUID("22000000-0000-7000-8000-000000000049"),
    "shipment:deliver": UUID("22000000-0000-7000-8000-000000000050"),
}
ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "admin": UUID("21000000-0000-7000-8000-000000000002"),
    "store_owner": UUID("21000000-0000-7000-8000-000000000003"),
    "store_staff": UUID("21000000-0000-7000-8000-000000000004"),
    "customer": UUID("21000000-0000-7000-8000-000000000005"),
}
STATUSES = (
    "created",
    "ready_for_fulfillment",
    "packed",
    "shipped",
    "out_for_delivery",
    "delivered",
    "cancelled",
    "return_requested",
    "returned",
)


def upgrade() -> None:
    op.create_table(
        "shipments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("reservation_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*STATUSES, native_enum=False),
            server_default="created",
            nullable=False,
        ),
        sa.Column("carrier", sa.String(length=100), nullable=True),
        sa.Column("tracking_number", sa.String(length=255), nullable=True),
        sa.Column("tracking_url", sa.String(length=2048), nullable=True),
        sa.Column("shipping_method", sa.String(length=100), nullable=False),
        sa.Column("estimated_delivery_at", sa.DateTime(timezone=True)),
        sa.Column("shipped_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
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
        sa.Column("created_by_id", sa.Uuid()),
        sa.Column("updated_by_id", sa.Uuid()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by_id", sa.Uuid()),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "(status NOT IN ('shipped', 'out_for_delivery', 'delivered', "
            "'return_requested', 'returned') OR shipped_at IS NOT NULL)",
            name="shipped_timestamp",
        ),
        sa.CheckConstraint(
            "(status != 'delivered' OR delivered_at IS NOT NULL)",
            name="delivered_timestamp",
        ),
        sa.CheckConstraint(
            "(status != 'cancelled' OR deleted_at IS NOT NULL)",
            name="cancelled_archive",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reservation_id"], ["inventory_reservations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payment_intents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_shipments_order"),
        sa.UniqueConstraint("reservation_id", name="uq_shipments_reservation"),
    )
    for name, columns in (
        ("ix_shipments_payment", ["payment_id"]),
        ("ix_shipments_customer", ["customer_id"]),
        ("ix_shipments_store", ["store_id"]),
        ("ix_shipments_status", ["status"]),
    ):
        op.create_index(name, "shipments", columns)

    op.create_table(
        "shipment_packages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("package_number", sa.String(length=100), nullable=False),
        sa.Column("weight", sa.Numeric(12, 3), nullable=False),
        sa.Column("length", sa.Numeric(12, 3), nullable=False),
        sa.Column("width", sa.Numeric(12, 3), nullable=False),
        sa.Column("height", sa.Numeric(12, 3), nullable=False),
        sa.Column("label_url", sa.String(length=2048)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("weight > 0", name="weight_positive"),
        sa.CheckConstraint(
            "length > 0 AND width > 0 AND height > 0", name="dimensions_positive"
        ),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shipment_id", "package_number", name="uq_shipment_packages_number"
        ),
    )
    op.create_index(
        "ix_shipment_packages_shipment", "shipment_packages", ["shipment_id"]
    )

    op.create_table(
        "shipment_tracking_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Enum(*STATUSES, native_enum=False), nullable=False),
        sa.Column("location", sa.String(length=255)),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_shipment_tracking_events_shipment",
        "shipment_tracking_events",
        ["shipment_id"],
    )
    op.create_index(
        "ix_shipment_tracking_events_occurred_at",
        "shipment_tracking_events",
        ["occurred_at"],
    )
    _seed_permissions()


def downgrade() -> None:
    _remove_permissions()
    op.drop_index(
        "ix_shipment_tracking_events_occurred_at",
        table_name="shipment_tracking_events",
    )
    op.drop_index(
        "ix_shipment_tracking_events_shipment",
        table_name="shipment_tracking_events",
    )
    op.drop_table("shipment_tracking_events")
    op.drop_index("ix_shipment_packages_shipment", table_name="shipment_packages")
    op.drop_table("shipment_packages")
    for name in (
        "ix_shipments_status",
        "ix_shipments_store",
        "ix_shipments_customer",
        "ix_shipments_payment",
    ):
        op.drop_index(name, table_name="shipments")
    op.drop_table("shipments")


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
                "description": f"Shipment permission for {name}.",
                "resource": "shipment",
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
    permission_ids = tuple(PERMISSIONS.values())
    role_permissions = sa.table(
        "identity_role_permissions",
        sa.column("permission_id", sa.Uuid()),
    )
    permissions = sa.table("identity_permissions", sa.column("id", sa.Uuid()))
    bind.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id.in_(permission_ids)
        )
    )
    bind.execute(sa.delete(permissions).where(permissions.c.id.in_(permission_ids)))
