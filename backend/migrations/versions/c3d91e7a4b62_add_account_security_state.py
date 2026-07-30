"""add account security state

Revision ID: c3d91e7a4b62
Revises: f25a7c19e4d0
Create Date: 2026-07-30 20:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d91e7a4b62"
down_revision: str | Sequence[str] | None = "f25a7c19e4d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add bounded progressive-lockout persistence and cleanup indexes."""
    op.add_column(
        "identity_users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "identity_users",
        sa.Column("lock_reason", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "identity_users",
        sa.Column(
            "unlock_count",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "unlock_count_nonnegative",
        "identity_users",
        "unlock_count >= 0",
    )
    op.create_index(
        "ix_identity_users_locked_until",
        "identity_users",
        ["locked_until"],
        unique=False,
        postgresql_where=sa.text("is_locked"),
    )
    op.create_index(
        "ix_identity_email_verification_tokens_expiry_cleanup",
        "identity_email_verification_tokens",
        ["expires_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_identity_password_reset_tokens_expiry_cleanup",
        "identity_password_reset_tokens",
        ["expires_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_identity_password_reset_tokens_expiry_cleanup",
        table_name="identity_password_reset_tokens",
    )
    op.drop_index(
        "ix_identity_email_verification_tokens_expiry_cleanup",
        table_name="identity_email_verification_tokens",
    )
    op.drop_index(
        "ix_identity_users_locked_until",
        table_name="identity_users",
    )
    op.drop_constraint(
        "ck_identity_users_unlock_count_nonnegative",
        "identity_users",
        type_="check",
    )
    op.drop_column("identity_users", "unlock_count")
    op.drop_column("identity_users", "lock_reason")
    op.drop_column("identity_users", "locked_until")
