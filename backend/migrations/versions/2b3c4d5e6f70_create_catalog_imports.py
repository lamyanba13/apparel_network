"""create retailer catalog imports

Revision ID: 2b3c4d5e6f70
Revises: f08c2d4e6a71
Create Date: 2026-08-09 00:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2b3c4d5e6f70"
down_revision: str | Sequence[str] | None = "f08c2d4e6a71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_TYPES = ("pos", "manual", "platform_staff", "spreadsheet")
IMPORT_STATUSES = (
    "created",
    "validating",
    "validated",
    "processing",
    "completed",
    "validation_failed",
    "failed",
)
ROW_ACTIONS = ("create", "update", "skip", "conflict", "error")
ROW_STATUSES = ("pending", "valid", "invalid", "completed", "failed")
ERROR_SEVERITIES = ("error", "warning")


def upgrade() -> None:
    op.add_column("product_media", sa.Column("variant_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_product_media_variant_id_product_variants",
        "product_media",
        "product_variants",
        ["variant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_product_media_variant", "product_media", ["variant_id"])

    op.create_table(
        "catalog_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source_type", sa.Enum(*SOURCE_TYPES, native_enum=False), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(*IMPORT_STATUSES, native_enum=False),
            server_default="created",
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("spreadsheet_checksum", sa.String(length=64), nullable=True),
        sa.Column("spreadsheet_content_type", sa.String(length=150), nullable=True),
        sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("invalid_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("successful_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("warning_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("version >= 1", name="catalog_imports_version_positive"),
        sa.CheckConstraint(
            "total_rows >= 0 AND valid_rows >= 0 AND invalid_rows >= 0 "
            "AND successful_rows >= 0 AND failed_rows >= 0 "
            "AND error_count >= 0 AND warning_count >= 0",
            name="catalog_imports_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "valid_rows + invalid_rows <= total_rows",
            name="catalog_imports_validation_counts_bounded",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["catalog_id"], ["catalogs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id", "idempotency_key", name="uq_catalog_imports_idempotency"
        ),
    )
    for name, columns in (
        ("ix_catalog_imports_store", ["store_id"]),
        ("ix_catalog_imports_catalog", ["catalog_id"]),
        ("ix_catalog_imports_actor", ["actor_id"]),
        ("ix_catalog_imports_status", ["status"]),
        ("ix_catalog_imports_source", ["source_type"]),
        ("ix_catalog_imports_created", ["created_at"]),
        ("ix_catalog_imports_store_created", ["store_id", "created_at"]),
    ):
        op.create_index(name, "catalog_imports", columns)

    op.create_table(
        "catalog_import_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("normalized_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(*ROW_ACTIONS, native_enum=False),
            server_default="skip",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(*ROW_STATUSES, native_enum=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("price_id", sa.Uuid(), nullable=True),
        sa.Column("inventory_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["import_id"], ["catalog_imports.id"], ondelete="CASCADE"
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
            "import_id", "row_number", name="uq_catalog_import_rows_number"
        ),
    )
    op.create_index(
        "ix_catalog_import_rows_import", "catalog_import_rows", ["import_id"]
    )
    op.create_index(
        "ix_catalog_import_rows_status", "catalog_import_rows", ["import_id", "status"]
    )
    op.create_index(
        "ix_catalog_import_rows_action", "catalog_import_rows", ["import_id", "action"]
    )

    op.create_table(
        "catalog_import_errors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("row_id", sa.Uuid(), nullable=True),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("field", sa.String(length=100), nullable=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "severity", sa.Enum(*ERROR_SEVERITIES, native_enum=False), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["import_id"], ["catalog_imports.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["row_id"], ["catalog_import_rows.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_catalog_import_errors_import", "catalog_import_errors", ["import_id"]
    )
    op.create_index(
        "ix_catalog_import_errors_row",
        "catalog_import_errors",
        ["import_id", "row_number"],
    )
    op.create_index(
        "ix_catalog_import_errors_severity",
        "catalog_import_errors",
        ["import_id", "severity"],
    )

    op.create_table(
        "catalog_import_media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("file_size > 0", name="catalog_import_media_size_positive"),
        sa.CheckConstraint(
            "width > 0 AND height > 0",
            name="catalog_import_media_dimensions_positive",
        ),
        sa.ForeignKeyConstraint(
            ["import_id"], ["catalog_imports.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_id", "filename", name="uq_catalog_import_media_filename"
        ),
        sa.UniqueConstraint(
            "import_id", "checksum_sha256", name="uq_catalog_import_media_checksum"
        ),
    )
    op.create_index(
        "ix_catalog_import_media_import", "catalog_import_media", ["import_id"]
    )
    op.create_index(
        "ix_catalog_import_media_checksum",
        "catalog_import_media",
        ["checksum_sha256"],
    )


def downgrade() -> None:
    op.drop_table("catalog_import_media")
    op.drop_table("catalog_import_errors")
    op.drop_table("catalog_import_rows")
    op.drop_table("catalog_imports")
    op.drop_index("ix_product_media_variant", table_name="product_media")
    op.drop_constraint(
        "fk_product_media_variant_id_product_variants",
        "product_media",
        type_="foreignkey",
    )
    op.drop_column("product_media", "variant_id")
