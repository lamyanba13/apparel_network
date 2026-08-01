"""add collection type foundation"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e12f4a6b8c90"
down_revision: str | Sequence[str] | None = "d94e2f7a1b05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column(
            "collection_type",
            sa.Enum("manual", "smart", "seasonal", "featured", native_enum=False),
            server_default="manual",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("collections", "collection_type")
