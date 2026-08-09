"""create append-only inventory movements

Revision ID: f08c2d4e6a71
Revises: ee6a8b0d2f35
Create Date: 2026-08-08 00:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f08c2d4e6a71"
down_revision: str | Sequence[str] | None = "ee6a8b0d2f35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MOVEMENT_TYPES = (
    "initial_stock",
    "manual_increase",
    "manual_decrease",
    "damage",
    "loss",
    "found",
    "correction",
    "reconciliation",
    "reservation_consumption",
    "legacy_update",
)


def upgrade() -> None:
    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inventory_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "movement_type",
            sa.Enum(*MOVEMENT_TYPES, native_enum=False),
            nullable=False,
        ),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("previous_on_hand", sa.Integer(), nullable=False),
        sa.Column("new_on_hand", sa.Integer(), nullable=False),
        sa.Column("previous_available", sa.Integer(), nullable=False),
        sa.Column("new_available", sa.Integer(), nullable=False),
        sa.Column("reservation_quantity", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "new_on_hand = previous_on_hand + quantity_delta",
            name="inventory_movement_on_hand_delta",
        ),
        sa.CheckConstraint(
            "previous_on_hand >= 0 AND new_on_hand >= 0",
            name="inventory_movement_on_hand_nonnegative",
        ),
        sa.CheckConstraint(
            "previous_available >= 0 AND new_available >= 0",
            name="inventory_movement_available_nonnegative",
        ),
        sa.CheckConstraint(
            "reservation_quantity >= 0",
            name="inventory_movement_reservation_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_id"], ["inventory_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["product_variants.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_inventory_movements_inventory_created", ["inventory_id", "created_at"]),
        ("ix_inventory_movements_store_created", ["store_id", "created_at"]),
        ("ix_inventory_movements_variant_created", ["variant_id", "created_at"]),
        ("ix_inventory_movements_type_created", ["movement_type", "created_at"]),
        ("ix_inventory_movements_actor_created", ["actor_id", "created_at"]),
        ("ix_inventory_movements_reference", ["source", "reference_id"]),
    ):
        op.create_index(name, "inventory_movements", columns)


def downgrade() -> None:
    op.drop_table("inventory_movements")
