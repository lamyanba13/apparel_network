"""create product media"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f43b2c1d9e80"
down_revision: str | Sequence[str] | None = "e12f4a6b8c90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("product_media",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False), sa.Column("catalog_id", sa.Uuid(), nullable=False),
        sa.Column("media_type", sa.Enum("image", "video", native_enum=False), nullable=False),
        sa.Column("role", sa.Enum("primary", "gallery", "thumbnail", "document", native_enum=False), nullable=False),
        sa.Column("storage_provider", sa.String(32), server_default="minio", nullable=False),
        sa.Column("bucket", sa.String(255), nullable=False), sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False), sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("extension", sa.String(10), nullable=False), sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer()), sa.Column("height", sa.Integer()), sa.Column("duration_seconds", sa.Integer()),
        sa.Column("checksum_sha256", sa.String(64), nullable=False), sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False), sa.Column("created_by_id", sa.Uuid()), sa.Column("updated_by_id", sa.Uuid()),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["catalog_id"], ["catalogs.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("object_key", name="uq_product_media_object_key"),
        sa.CheckConstraint("file_size > 0", name="product_media_file_size_positive"), sa.CheckConstraint("(width IS NULL OR width > 0) AND (height IS NULL OR height > 0)", name="product_media_dimensions_positive"), sa.CheckConstraint("duration_seconds IS NULL OR duration_seconds > 0", name="product_media_duration_positive"), sa.CheckConstraint("display_order >= 0", name="product_media_display_order_nonnegative"), sa.CheckConstraint("version >= 1", name="product_media_version_positive"), sa.CheckConstraint("deleted_at IS NULL OR is_active = false", name="product_media_soft_delete_consistent"))
    for name, columns in (("ix_product_media_product", ["product_id"]), ("ix_product_media_store", ["store_id"]), ("ix_product_media_catalog", ["catalog_id"]), ("ix_product_media_product_role", ["product_id", "role"]), ("ix_product_media_product_order", ["product_id", "display_order"])):
        op.create_index(name, "product_media", columns)
    op.create_index("uq_product_media_primary", "product_media", ["product_id"], unique=True, postgresql_where=sa.text("role = 'primary' AND media_type = 'image' AND is_active = true AND deleted_at IS NULL"))
    op.create_index("uq_product_media_checksum", "product_media", ["product_id", "checksum_sha256"], unique=True, postgresql_where=sa.text("is_active = true AND deleted_at IS NULL"))


def downgrade() -> None:
    for name in ("uq_product_media_checksum", "uq_product_media_primary", "ix_product_media_product_order", "ix_product_media_product_role", "ix_product_media_catalog", "ix_product_media_store", "ix_product_media_product"):
        op.drop_index(name, table_name="product_media")
    op.drop_table("product_media")
