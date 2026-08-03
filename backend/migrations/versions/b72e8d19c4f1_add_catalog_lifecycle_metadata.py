"""add catalog lifecycle metadata"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b72e8d19c4f1"
down_revision: str | Sequence[str] | None = "a91c7d4e2f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("catalogs", sa.Column("activated_at", sa.DateTime(timezone=True)))
    op.add_column("catalogs", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column(
        "catalogs",
        sa.Column(
            "is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.create_check_constraint(
        "catalogs_default_active", "catalogs", "is_default = false OR status = 'active'"
    )
    op.create_index(
        "ix_catalogs_default_active",
        "catalogs",
        ["store_id"],
        unique=True,
        postgresql_where=sa.text(
            "is_default = true AND status = 'active' AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_catalogs_default_active", table_name="catalogs")
    op.drop_constraint("catalogs_default_active", "catalogs", type_="check")
    op.drop_column("catalogs", "is_default")
    op.drop_column("catalogs", "archived_at")
    op.drop_column("catalogs", "activated_at")
