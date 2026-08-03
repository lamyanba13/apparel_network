"""create catalog foundation"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a91c7d4e2f10"
down_revision: str | Sequence[str] | None = "0f01b7088f73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalogs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
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
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "slug", name="uq_catalogs_store_slug"),
        sa.CheckConstraint("version >= 1", name="catalogs_version_positive"),
        sa.CheckConstraint("sort_order >= 0", name="catalogs_sort_order_non_negative"),
        sa.CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'",
            name="catalogs_deleted_archived",
        ),
    )
    for name, columns in (
        ("ix_catalogs_store_id", ["store_id"]),
        ("ix_catalogs_store_status", ["store_id", "status"]),
        ("ix_catalogs_store_visibility", ["store_id", "visibility"]),
        ("ix_catalogs_store_sort_order", ["store_id", "sort_order"]),
        ("ix_catalogs_slug", ["slug"]),
    ):
        op.create_index(name, "catalogs", columns)


def downgrade() -> None:
    for name in (
        "ix_catalogs_slug",
        "ix_catalogs_store_sort_order",
        "ix_catalogs_store_visibility",
        "ix_catalogs_store_status",
        "ix_catalogs_store_id",
    ):
        op.drop_index(name, table_name="catalogs")
    op.drop_table("catalogs")
