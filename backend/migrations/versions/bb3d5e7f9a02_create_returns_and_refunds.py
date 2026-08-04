"""create returns and refunds

Revision ID: bb3d5e7f9a02
Revises: aa2c4d6e8f91
Create Date: 2026-08-05 00:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "bb3d5e7f9a02"
down_revision: str | Sequence[str] | None = "aa2c4d6e8f91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    name: UUID(f"22000000-0000-7000-8000-{suffix:012d}")
    for suffix, name in enumerate(
        (
            "return:create",
            "return:view",
            "return:update",
            "return:approve",
            "return:receive",
            "return:inspect",
            "return:reject",
            "refund:create",
            "refund:view",
            "refund:process",
        ),
        start=51,
    )
}
ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "admin": UUID("21000000-0000-7000-8000-000000000002"),
    "store_owner": UUID("21000000-0000-7000-8000-000000000003"),
    "store_staff": UUID("21000000-0000-7000-8000-000000000004"),
    "customer": UUID("21000000-0000-7000-8000-000000000005"),
}
CUSTOMER_PERMISSIONS = {
    "return:create",
    "return:view",
    "return:update",
    "refund:create",
    "refund:view",
}
RETURN_STATUSES = (
    "requested",
    "approved",
    "received",
    "inspected",
    "refund_pending",
    "refunded",
    "rejected",
    "cancelled",
)
REFUND_STATUSES = ("pending", "processing", "completed", "failed")
DISPOSITIONS = ("restock", "damaged", "inspection_required", "dispose")
TRANSACTION_TYPES = ("created", "processing", "completed", "failed")


def upgrade() -> None:
    op.create_table(
        "returns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*RETURN_STATUSES, native_enum=False),
            server_default="requested",
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("inspected_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
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
            "(status != 'approved' OR approved_at IS NOT NULL) AND "
            "(status NOT IN ('received', 'inspected', 'refund_pending', 'refunded') "
            "OR received_at IS NOT NULL) AND "
            "(status NOT IN ('inspected', 'refund_pending', 'refunded') "
            "OR inspected_at IS NOT NULL) AND "
            "(status != 'rejected' OR rejected_at IS NOT NULL) AND "
            "(status != 'cancelled' OR cancelled_at IS NOT NULL)",
            name="lifecycle_timestamps",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payment_intents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_returns_order", ["order_id"]),
        ("ix_returns_shipment", ["shipment_id"]),
        ("ix_returns_payment", ["payment_id"]),
        ("ix_returns_customer", ["customer_id"]),
        ("ix_returns_store", ["store_id"]),
        ("ix_returns_status", ["status"]),
    ):
        op.create_index(name, "returns", columns)

    op.create_table(
        "return_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("return_id", sa.Uuid(), nullable=False),
        sa.Column("order_item_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "disposition",
            sa.Enum(*DISPOSITIONS, native_enum=False),
            server_default="inspection_required",
            nullable=False,
        ),
        sa.Column("inspected_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        sa.ForeignKeyConstraint(["return_id"], ["returns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["order_item_id"], ["order_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["product_variants.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"], ["inventory_items.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "return_id", "order_item_id", name="uq_return_items_order_item"
        ),
    )
    for name, columns in (
        ("ix_return_items_return", ["return_id"]),
        ("ix_return_items_order_item", ["order_item_id"]),
        ("ix_return_items_inventory", ["inventory_item_id"]),
    ):
        op.create_index(name, "return_items", columns)

    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("return_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*REFUND_STATUSES, native_enum=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_reference", sa.String(length=255)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
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
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "(status != 'completed' OR completed_at IS NOT NULL) AND "
            "(status != 'failed' OR failed_at IS NOT NULL)",
            name="lifecycle_timestamps",
        ),
        sa.ForeignKeyConstraint(["return_id"], ["returns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payment_intents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("return_id", name="uq_refunds_return"),
    )
    for name, columns in (
        ("ix_refunds_payment", ["payment_id"]),
        ("ix_refunds_customer", ["customer_id"]),
        ("ix_refunds_store", ["store_id"]),
        ("ix_refunds_status", ["status"]),
    ):
        op.create_index(name, "refunds", columns)

    op.create_table(
        "refund_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("refund_id", sa.Uuid(), nullable=False),
        sa.Column("provider_transaction_id", sa.String(length=255), nullable=False),
        sa.Column(
            "event_type", sa.Enum(*TRANSACTION_TYPES, native_enum=False), nullable=False
        ),
        sa.Column(
            "status", sa.Enum(*REFUND_STATUSES, native_enum=False), nullable=False
        ),
        sa.Column(
            "provider_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["refund_id"], ["refunds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_transaction_id", name="uq_refund_transactions_provider_id"
        ),
    )
    op.create_index(
        "ix_refund_transactions_refund", "refund_transactions", ["refund_id"]
    )
    op.create_index(
        "ix_refund_transactions_occurred_at",
        "refund_transactions",
        ["occurred_at"],
    )
    _seed_permissions()


def downgrade() -> None:
    _remove_permissions()
    op.drop_index(
        "ix_refund_transactions_occurred_at", table_name="refund_transactions"
    )
    op.drop_index("ix_refund_transactions_refund", table_name="refund_transactions")
    op.drop_table("refund_transactions")
    for name in (
        "ix_refunds_status",
        "ix_refunds_store",
        "ix_refunds_customer",
        "ix_refunds_payment",
    ):
        op.drop_index(name, table_name="refunds")
    op.drop_table("refunds")
    for name in (
        "ix_return_items_inventory",
        "ix_return_items_order_item",
        "ix_return_items_return",
    ):
        op.drop_index(name, table_name="return_items")
    op.drop_table("return_items")
    for name in (
        "ix_returns_status",
        "ix_returns_store",
        "ix_returns_customer",
        "ix_returns_payment",
        "ix_returns_shipment",
        "ix_returns_order",
    ):
        op.drop_index(name, table_name="returns")
    op.drop_table("returns")


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
                "description": f"Returns permission for {name}.",
                "resource": name.split(":", maxsplit=1)[0],
                "action": name.split(":", maxsplit=1)[1],
            }
            for name, permission_id in PERMISSIONS.items()
        ],
    )
    grants = []
    for role_name, role_id in ROLE_IDS.items():
        for name, permission_id in PERMISSIONS.items():
            if role_name != "customer" or name in CUSTOMER_PERMISSIONS:
                grants.append({"role_id": role_id, "permission_id": permission_id})
    op.bulk_insert(role_permissions, grants)


def _remove_permissions() -> None:
    bind = op.get_bind()
    permission_ids = tuple(PERMISSIONS.values())
    role_permissions = sa.table(
        "identity_role_permissions", sa.column("permission_id", sa.Uuid())
    )
    permissions = sa.table("identity_permissions", sa.column("id", sa.Uuid()))
    bind.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id.in_(permission_ids)
        )
    )
    bind.execute(sa.delete(permissions).where(permissions.c.id.in_(permission_ids)))
