"""create price lists

Revision ID: 3a5b7d9f1c24
Revises: 2f4a6c8e0b12
Create Date: 2026-08-03 21:00:00+00:00
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "3a5b7d9f1c24"
down_revision: str | Sequence[str] | None = "2f4a6c8e0b12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "price:list:create": UUID("22000000-0000-7000-8000-000000000017"),
    "price:list:view": UUID("22000000-0000-7000-8000-000000000018"),
    "price:list:update": UUID("22000000-0000-7000-8000-000000000019"),
    "price:resolve": UUID("22000000-0000-7000-8000-000000000020"),
}
ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "store_owner": UUID("21000000-0000-7000-8000-000000000003"),
    "store_staff": UUID("21000000-0000-7000-8000-000000000004"),
}
GRANTS = {
    "super_admin": set(PERMISSIONS),
    "store_owner": set(PERMISSIONS),
    "store_staff": {"price:list:view", "price:list:update", "price:resolve"},
}


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_identity_permissions_resource_canonical"),
        "identity_permissions",
        type_="check",
    )
    op.create_check_constraint(
        "resource_canonical",
        "identity_permissions",
        "resource ~ '^[a-z][a-z0-9_]{0,99}" "(:[a-z][a-z0-9_]{0,99})*$'",
    )
    op.create_table(
        "price_lists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "archived", native_enum=False),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "customer_group",
            sa.Enum(
                "public",
                "wholesale",
                "vip",
                "staff",
                "custom",
                native_enum=False,
            ),
            server_default="public",
            nullable=False,
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("priority >= 0", name="priority_nonnegative"),
        sa.CheckConstraint(
            "effective_from IS NULL OR effective_until IS NULL "
            "OR effective_from < effective_until",
            name="effective_period",
        ),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'", name="deleted_archived"
        ),
        sa.CheckConstraint(
            "is_default = false OR status = 'active'", name="default_active"
        ),
        sa.CheckConstraint(
            "is_default = false OR customer_group = 'public'", name="default_public"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "slug", name="uq_price_lists_store_slug"),
    )
    for name, columns in (
        ("ix_price_lists_store", ["store_id"]),
        ("ix_price_lists_currency", ["currency_code"]),
        ("ix_price_lists_priority", ["priority"]),
        ("ix_price_lists_status", ["status"]),
        ("ix_price_lists_effective_from", ["effective_from"]),
        ("ix_price_lists_effective_until", ["effective_until"]),
    ):
        op.create_index(name, "price_lists", columns)
    op.create_index(
        "uq_price_lists_default_store_currency",
        "price_lists",
        ["store_id", "currency_code"],
        unique=True,
        postgresql_where=sa.text("is_default = true AND deleted_at IS NULL"),
    )

    op.create_table(
        "price_list_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("price_list_id", sa.Uuid(), nullable=False),
        sa.Column("price_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["price_list_id"], ["price_lists.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["price_id"], ["product_prices.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "price_list_id",
            "price_id",
            name="uq_price_list_assignments_price_list_price",
        ),
    )
    op.create_index(
        "ix_price_list_assignments_price_list",
        "price_list_assignments",
        ["price_list_id"],
    )
    op.create_index(
        "ix_price_list_assignments_price",
        "price_list_assignments",
        ["price_id"],
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
                "description": f"Price List permission for {name}.",
                "resource": ":".join(name.split(":")[:-1]),
                "action": name.rsplit(":", maxsplit=1)[1],
            }
            for name, permission_id in PERMISSIONS.items()
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": ROLE_IDS[role], "permission_id": PERMISSIONS[permission]}
            for role, grants in GRANTS.items()
            for permission in sorted(grants)
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    role_permissions = sa.table(
        "identity_role_permissions", sa.column("permission_id", sa.Uuid())
    )
    permissions = sa.table("identity_permissions", sa.column("id", sa.Uuid()))
    permission_ids = tuple(PERMISSIONS.values())
    bind.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id.in_(permission_ids)
        )
    )
    bind.execute(sa.delete(permissions).where(permissions.c.id.in_(permission_ids)))

    op.drop_constraint(
        op.f("ck_identity_permissions_resource_canonical"),
        "identity_permissions",
        type_="check",
    )
    op.create_check_constraint(
        "resource_canonical",
        "identity_permissions",
        "resource ~ '^[a-z][a-z0-9_]{0,99}$'",
    )

    op.drop_index(
        "ix_price_list_assignments_price", table_name="price_list_assignments"
    )
    op.drop_index(
        "ix_price_list_assignments_price_list", table_name="price_list_assignments"
    )
    op.drop_table("price_list_assignments")
    op.drop_index("uq_price_lists_default_store_currency", table_name="price_lists")
    for name in (
        "ix_price_lists_effective_until",
        "ix_price_lists_effective_from",
        "ix_price_lists_status",
        "ix_price_lists_priority",
        "ix_price_lists_currency",
        "ix_price_lists_store",
    ):
        op.drop_index(name, table_name="price_lists")
    op.drop_table("price_lists")
