"""add session lifecycle metadata

Revision ID: d41f63a709b2
Revises: a9c2cc1d183e
Create Date: 2026-07-30 15:30:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d41f63a709b2"
down_revision: str | Sequence[str] | None = "a9c2cc1d183e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the reviewed Phase 2.3 additive schema change."""
    table = "identity_refresh_sessions"
    op.add_column(
        table,
        sa.Column(
            "display_name",
            sa.String(length=120),
            server_default="Unknown device",
            nullable=False,
        ),
    )
    op.add_column(
        table,
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(table, sa.Column("last_ip", postgresql.INET(), nullable=True))
    op.add_column(
        table, sa.Column("last_user_agent", sa.String(length=1024), nullable=True)
    )
    op.add_column(
        table, sa.Column("last_browser", sa.String(length=120), nullable=True)
    )
    op.add_column(
        table,
        sa.Column("last_operating_system", sa.String(length=120), nullable=True),
    )
    op.add_column(
        table, sa.Column("last_device_type", sa.String(length=40), nullable=True)
    )
    op.add_column(table, sa.Column("platform", sa.String(length=80), nullable=True))
    op.add_column(table, sa.Column("city", sa.String(length=120), nullable=True))
    op.add_column(
        table,
        sa.Column(
            "is_trusted",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_identity_refresh_sessions_display_name_length"),
        table,
        "length(btrim(display_name)) BETWEEN 1 AND 120",
    )
    op.create_index(
        "ix_identity_refresh_sessions_cleanup",
        table,
        ["expires_at", "id"],
        unique=False,
        postgresql_where=sa.text("is_revoked"),
    )


def downgrade() -> None:
    """Reverse Phase 2.3 metadata when rollback has been approved."""
    table = "identity_refresh_sessions"
    op.drop_index("ix_identity_refresh_sessions_cleanup", table_name=table)
    op.drop_constraint(
        op.f("ck_identity_refresh_sessions_display_name_length"),
        table,
        type_="check",
    )
    for column in (
        "is_trusted",
        "city",
        "platform",
        "last_device_type",
        "last_operating_system",
        "last_browser",
        "last_user_agent",
        "last_ip",
        "last_seen_at",
        "display_name",
    ):
        op.drop_column(table, column)
