"""create product variants"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "697a9e0d3c1b"
down_revision: str | Sequence[str] | None = "f43b2c1d9e80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column(
            "attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("attribute_signature", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
        sa.CheckConstraint(
            "sort_order >= 0", name="product_variants_sort_order_nonnegative"
        ),
        sa.CheckConstraint("version >= 1", name="product_variants_version_positive"),
        sa.CheckConstraint(
            "char_length(attribute_signature) = 64",
            name="product_variants_signature_length",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_variants_product", "product_variants", ["product_id"])
    op.create_index("ix_product_variants_store", "product_variants", ["store_id"])
    op.create_index(
        "ix_product_variants_product_order",
        "product_variants",
        ["product_id", "sort_order"],
    )
    op.create_index(
        "uq_product_variants_store_reference",
        "product_variants",
        ["store_id", "reference"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_product_variants_product_signature",
        "product_variants",
        ["product_id", "attribute_signature"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_product_variants_product_signature", table_name="product_variants"
    )
    op.drop_index("uq_product_variants_store_reference", table_name="product_variants")
    op.drop_index("ix_product_variants_product_order", table_name="product_variants")
    op.drop_index("ix_product_variants_store", table_name="product_variants")
    op.drop_index("ix_product_variants_product", table_name="product_variants")
    op.drop_table("product_variants")
