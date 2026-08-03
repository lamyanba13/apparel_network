"""create product prices

Revision ID: 2f4a6c8e0b12
Revises: 1d2e3f4a5b6c
Create Date: 2026-08-03 17:00:00+00:00
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "2f4a6c8e0b12"
down_revision: str | Sequence[str] | None = "1d2e3f4a5b6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "price:create": UUID("22000000-0000-7000-8000-000000000014"),
    "price:view": UUID("22000000-0000-7000-8000-000000000015"),
    "price:update": UUID("22000000-0000-7000-8000-000000000016"),
}
ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "store_owner": UUID("21000000-0000-7000-8000-000000000003"),
    "store_staff": UUID("21000000-0000-7000-8000-000000000004"),
}
GRANTS = {
    "super_admin": set(PERMISSIONS),
    "store_owner": set(PERMISSIONS),
    "store_staff": {"price:view", "price:update"},
}


def upgrade() -> None:
    op.create_table(
        "product_prices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("base_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("sale_price", sa.Numeric(19, 4), nullable=True),
        sa.Column("compare_at_price", sa.Numeric(19, 4), nullable=True),
        sa.Column("cost_price", sa.Numeric(19, 4), nullable=True),
        sa.Column("tax_class", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "archived", native_enum=False),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("base_price >= 0", name="base_nonnegative"),
        sa.CheckConstraint("sale_price >= 0", name="sale_nonnegative"),
        sa.CheckConstraint("compare_at_price >= 0", name="compare_nonnegative"),
        sa.CheckConstraint("cost_price >= 0", name="cost_nonnegative"),
        sa.CheckConstraint(
            "sale_price IS NULL OR sale_price <= base_price",
            name="sale_not_above_base",
        ),
        sa.CheckConstraint(
            "compare_at_price IS NULL OR compare_at_price >= base_price",
            name="compare_not_below_base",
        ),
        sa.CheckConstraint(
            "effective_from IS NULL OR effective_until IS NULL "
            "OR effective_from < effective_until",
            name="effective_period",
        ),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'",
            name="deleted_archived",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["product_variants.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_product_prices_store", ["store_id"]),
        ("ix_product_prices_product", ["product_id"]),
        ("ix_product_prices_variant", ["variant_id"]),
        ("ix_product_prices_status", ["status"]),
        ("ix_product_prices_currency", ["currency_code"]),
        ("ix_product_prices_effective_from", ["effective_from"]),
        ("ix_product_prices_effective_until", ["effective_until"]),
    ):
        op.create_index(name, "product_prices", columns)
    op.create_index(
        "uq_product_prices_active_variant_currency_period",
        "product_prices",
        ["variant_id", "currency_code", "effective_from", "effective_until"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'active' AND variant_id IS NOT NULL AND deleted_at IS NULL"
        ),
        postgresql_nulls_not_distinct=True,
    )

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
                "description": f"Product Pricing permission for {name}.",
                "resource": "price",
                "action": name.split(":", maxsplit=1)[1],
            }
            for name, permission_id in PERMISSIONS.items()
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            {
                "role_id": ROLE_IDS[role],
                "permission_id": PERMISSIONS[permission],
            }
            for role, grants in GRANTS.items()
            for permission in sorted(grants)
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    role_permissions = sa.table(
        "identity_role_permissions",
        sa.column("permission_id", sa.Uuid()),
    )
    permissions = sa.table("identity_permissions", sa.column("id", sa.Uuid()))
    permission_ids = tuple(PERMISSIONS.values())
    bind.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id.in_(permission_ids)
        )
    )
    bind.execute(sa.delete(permissions).where(permissions.c.id.in_(permission_ids)))

    op.drop_index(
        "uq_product_prices_active_variant_currency_period",
        table_name="product_prices",
    )
    for name in (
        "ix_product_prices_effective_until",
        "ix_product_prices_effective_from",
        "ix_product_prices_currency",
        "ix_product_prices_status",
        "ix_product_prices_variant",
        "ix_product_prices_product",
        "ix_product_prices_store",
    ):
        op.drop_index(name, table_name="product_prices")
    op.drop_table("product_prices")
