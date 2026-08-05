"""create promotions and discount engine

Revision ID: cc4e6f8a0b13
Revises: bb3d5e7f9a02
Create Date: 2026-08-05 00:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "cc4e6f8a0b13"
down_revision: str | Sequence[str] | None = "bb3d5e7f9a02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    name: UUID(f"22000000-0000-7000-8000-{suffix:012d}")
    for suffix, name in enumerate(
        (
            "promotion:create",
            "promotion:view",
            "promotion:update",
            "promotion:activate",
            "promotion:archive",
            "coupon:create",
            "coupon:view",
            "coupon:update",
            "coupon:redeem",
        ),
        start=61,
    )
}
ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "admin": UUID("21000000-0000-7000-8000-000000000002"),
    "store_owner": UUID("21000000-0000-7000-8000-000000000003"),
    "store_staff": UUID("21000000-0000-7000-8000-000000000004"),
    "customer": UUID("21000000-0000-7000-8000-000000000005"),
}
PROMOTION_STATUSES = ("draft", "active", "archived")
PROMOTION_TYPES = (
    "percentage",
    "fixed_amount",
    "buy_x_get_y",
    "bundle",
    "tier_discount",
    "free_shipping",
)
RULE_CONDITIONS = ("category", "brand", "catalog", "product", "variant")


def _lifecycle_columns() -> list[sa.Column[Any]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "promotions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "promotion_type",
            sa.Enum(*PROMOTION_TYPES, native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(*PROMOTION_STATUSES, native_enum=False),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3)),
        sa.Column("percentage", sa.Numeric(7, 4)),
        sa.Column("fixed_amount", sa.Numeric(19, 4)),
        sa.Column("buy_quantity", sa.Integer()),
        sa.Column("get_quantity", sa.Integer()),
        sa.Column("bundle_quantity", sa.Integer()),
        sa.Column("bundle_price", sa.Numeric(19, 4)),
        sa.Column(
            "tiers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("public", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "first_purchase_only",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("customer_group", sa.String(length=50)),
        sa.Column("minimum_order_amount", sa.Numeric(19, 4)),
        sa.Column("minimum_quantity", sa.Integer()),
        sa.Column("maximum_discount", sa.Numeric(19, 4)),
        sa.Column("usage_limit", sa.Integer()),
        sa.Column("per_customer_usage_limit", sa.Integer()),
        sa.Column("exclusive", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("stackable", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("maximum_stack", sa.Integer()),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_until", sa.DateTime(timezone=True)),
        *_lifecycle_columns(),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint("priority >= 0", name="priority_non_negative"),
        sa.CheckConstraint(
            "percentage IS NULL OR percentage BETWEEN 0 AND 100",
            name="percentage_range",
        ),
        sa.CheckConstraint(
            "fixed_amount IS NULL OR fixed_amount >= 0",
            name="fixed_amount_non_negative",
        ),
        sa.CheckConstraint(
            "maximum_discount IS NULL OR maximum_discount >= 0",
            name="maximum_discount_non_negative",
        ),
        sa.CheckConstraint(
            "minimum_order_amount IS NULL OR minimum_order_amount >= 0",
            name="minimum_order_non_negative",
        ),
        sa.CheckConstraint(
            "minimum_quantity IS NULL OR minimum_quantity > 0",
            name="minimum_quantity_positive",
        ),
        sa.CheckConstraint(
            "usage_limit IS NULL OR usage_limit > 0", name="usage_limit_positive"
        ),
        sa.CheckConstraint(
            "per_customer_usage_limit IS NULL OR per_customer_usage_limit > 0",
            name="customer_usage_limit_positive",
        ),
        sa.CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'", name="deleted_archived"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_promotions_store", ["store_id"]),
        ("ix_promotions_store_status", ["store_id", "status"]),
        ("ix_promotions_effective", ["effective_from", "effective_until"]),
        ("ix_promotions_priority", ["priority"]),
    ):
        op.create_index(name, "promotions", columns)

    op.create_table(
        "promotion_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("promotion_id", sa.Uuid(), nullable=False),
        sa.Column(
            "condition", sa.Enum(*RULE_CONDITIONS, native_enum=False), nullable=False
        ),
        sa.Column(
            "configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        *_lifecycle_columns(),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["promotion_id"], ["promotions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_promotion_rules_promotion", "promotion_rules", ["promotion_id"])
    op.create_index("ix_promotion_rules_condition", "promotion_rules", ["condition"])

    op.create_table(
        "promotion_coupons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("promotion_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_until", sa.DateTime(timezone=True)),
        sa.Column("usage_limit", sa.Integer()),
        sa.Column("per_customer_usage_limit", sa.Integer()),
        *_lifecycle_columns(),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "usage_limit IS NULL OR usage_limit > 0", name="usage_limit_positive"
        ),
        sa.CheckConstraint(
            "per_customer_usage_limit IS NULL OR per_customer_usage_limit > 0",
            name="customer_usage_limit_positive",
        ),
        sa.ForeignKeyConstraint(
            ["promotion_id"], ["promotions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "code", name="uq_promotion_coupons_store_code"),
    )
    op.create_index(
        "ix_promotion_coupons_promotion", "promotion_coupons", ["promotion_id"]
    )
    op.create_index("ix_promotion_coupons_store", "promotion_coupons", ["store_id"])
    op.create_index(
        "ix_promotion_coupons_active", "promotion_coupons", ["store_id", "active"]
    )

    op.create_table(
        "promotion_redemptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("promotion_id", sa.Uuid(), nullable=False),
        sa.Column("coupon_id", sa.Uuid()),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        sa.Column("checkout_session_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid()),
        sa.Column("discount_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("coupon_code", sa.String(length=64)),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False),
        *_lifecycle_columns(),
        sa.CheckConstraint("discount_amount >= 0", name="discount_non_negative"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["promotion_id"], ["promotions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["coupon_id"], ["promotion_coupons.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["cart_id"], ["shopping_carts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["checkout_session_id"], ["checkout_sessions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "checkout_session_id",
            "promotion_id",
            name="uq_promotion_redemptions_checkout_promotion",
        ),
    )
    for name, columns in (
        ("ix_promotion_redemptions_promotion", ["promotion_id"]),
        ("ix_promotion_redemptions_coupon", ["coupon_id"]),
        ("ix_promotion_redemptions_customer", ["customer_id"]),
        ("ix_promotion_redemptions_store", ["store_id"]),
        ("ix_promotion_redemptions_checkout", ["checkout_session_id"]),
        ("ix_promotion_redemptions_order", ["order_id"]),
    ):
        op.create_index(name, "promotion_redemptions", columns)

    op.create_table(
        "promotion_customer_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("promotion_id", sa.Uuid(), nullable=False),
        sa.Column("coupon_id", sa.Uuid()),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        *_lifecycle_columns(),
        sa.CheckConstraint("usage_count >= 0", name="usage_count_non_negative"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["promotion_id"], ["promotions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["coupon_id"], ["promotion_coupons.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["identity_users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "promotion_id",
            "coupon_id",
            "customer_id",
            name="uq_promotion_customer_usage_scope",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_promotion_customer_usage_promotion",
        "promotion_customer_usage",
        ["promotion_id"],
    )
    op.create_index(
        "ix_promotion_customer_usage_customer",
        "promotion_customer_usage",
        ["customer_id"],
    )
    op.create_index(
        "ix_promotion_customer_usage_store", "promotion_customer_usage", ["store_id"]
    )
    _seed_permissions()


def downgrade() -> None:
    _remove_permissions()
    op.drop_table("promotion_customer_usage")
    op.drop_table("promotion_redemptions")
    op.drop_table("promotion_coupons")
    op.drop_table("promotion_rules")
    op.drop_table("promotions")


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
                "description": f"Promotions permission for {name}.",
                "resource": name.split(":", maxsplit=1)[0],
                "action": name.split(":", maxsplit=1)[1],
            }
            for name, permission_id in PERMISSIONS.items()
        ],
    )
    grants = [
        {"role_id": role_id, "permission_id": permission_id}
        for role_name, role_id in ROLE_IDS.items()
        for name, permission_id in PERMISSIONS.items()
        if role_name != "customer" or name == "coupon:redeem"
    ]
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
