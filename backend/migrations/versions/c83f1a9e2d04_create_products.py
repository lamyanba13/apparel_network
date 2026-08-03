"""create product foundation"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c83f1a9e2d04"
down_revision: str | Sequence[str] | None = "b72e8d19c4f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("catalog_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("short_description", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "archived", native_enum=False),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "visibility",
            sa.Enum("public", "private", "hidden", native_enum=False),
            server_default="private",
            nullable=False,
        ),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("brand", sa.String(length=150), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["catalog_id"], ["catalogs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_id", "slug", name="uq_products_catalog_slug"),
        sa.UniqueConstraint("store_id", "sku", name="uq_products_store_sku"),
        sa.CheckConstraint("version >= 1", name="products_version_positive"),
        sa.CheckConstraint("sort_order >= 0", name="products_sort_order_non_negative"),
        sa.CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'",
            name="products_deleted_archived",
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 2 AND 200", name="products_name_length"
        ),
    )
    for name, columns in (
        ("ix_products_store_id", ["store_id"]),
        ("ix_products_catalog_id", ["catalog_id"]),
        ("ix_products_catalog_status", ["catalog_id", "status"]),
        ("ix_products_store_status", ["store_id", "status"]),
        ("ix_products_store_visibility", ["store_id", "visibility"]),
        ("ix_products_sku", ["sku"]),
        ("ix_products_slug", ["slug"]),
    ):
        op.create_index(name, "products", columns)


def downgrade() -> None:
    for name in (
        "ix_products_slug",
        "ix_products_sku",
        "ix_products_store_visibility",
        "ix_products_store_status",
        "ix_products_catalog_status",
        "ix_products_catalog_id",
        "ix_products_store_id",
    ):
        op.drop_index(name, table_name="products")
    op.drop_table("products")
