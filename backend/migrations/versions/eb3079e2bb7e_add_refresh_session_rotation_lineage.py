"""add refresh session rotation lineage

Revision ID: eb3079e2bb7e
Revises: b6d38dd509e1
Create Date: 2026-07-30 08:43:26.690000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "eb3079e2bb7e"
down_revision: str | Sequence[str] | None = "b6d38dd509e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the schema change."""
    op.add_column(
        "identity_refresh_sessions",
        sa.Column(
            "family_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.add_column(
        "identity_refresh_sessions",
        sa.Column("parent_session_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "identity_refresh_sessions",
        sa.Column(
            "rotation_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_identity_refresh_sessions_rotation_count_non_negative"),
        "identity_refresh_sessions",
        "rotation_count >= 0",
    )
    op.create_index(
        "ix_identity_refresh_sessions_family_id",
        "identity_refresh_sessions",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        "ix_identity_refresh_sessions_parent_session_id",
        "identity_refresh_sessions",
        ["parent_session_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f(
            "fk_identity_refresh_sessions_parent_session_id_identity_refresh_sessions"
        ),
        "identity_refresh_sessions",
        "identity_refresh_sessions",
        ["parent_session_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Reverse the schema change when it is proven safe."""
    op.drop_constraint(
        op.f(
            "fk_identity_refresh_sessions_parent_session_id_identity_refresh_sessions"
        ),
        "identity_refresh_sessions",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_identity_refresh_sessions_parent_session_id",
        table_name="identity_refresh_sessions",
    )
    op.drop_index(
        "ix_identity_refresh_sessions_family_id",
        table_name="identity_refresh_sessions",
    )
    op.drop_constraint(
        op.f("ck_identity_refresh_sessions_rotation_count_non_negative"),
        "identity_refresh_sessions",
        type_="check",
    )
    op.drop_column("identity_refresh_sessions", "rotation_count")
    op.drop_column("identity_refresh_sessions", "parent_session_id")
    op.drop_column("identity_refresh_sessions", "family_id")
