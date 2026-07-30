"""reserve session risk metadata

Revision ID: a9c2cc1d183e
Revises: eb3079e2bb7e
Create Date: 2026-07-30 09:39:53.926199+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9c2cc1d183e"
down_revision: str | Sequence[str] | None = "eb3079e2bb7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the schema change."""
    op.add_column(
        "identity_refresh_sessions",
        sa.Column("risk_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "identity_refresh_sessions",
        sa.Column("last_country", sa.String(length=2), nullable=True),
    )
    op.add_column(
        "identity_refresh_sessions",
        sa.Column("last_asn", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "identity_refresh_sessions",
        sa.Column(
            "last_device_fingerprint",
            sa.String(length=128),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f("ck_identity_refresh_sessions_risk_score_range"),
        "identity_refresh_sessions",
        "risk_score IS NULL OR risk_score BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        op.f("ck_identity_refresh_sessions_last_country_iso_alpha2"),
        "identity_refresh_sessions",
        "last_country IS NULL OR last_country ~ '^[A-Z]{2}$'",
    )
    op.create_check_constraint(
        op.f("ck_identity_refresh_sessions_last_asn_range"),
        "identity_refresh_sessions",
        "last_asn IS NULL OR last_asn BETWEEN 0 AND 4294967295",
    )
    op.create_check_constraint(
        op.f("ck_identity_refresh_sessions_last_device_fingerprint_length"),
        "identity_refresh_sessions",
        "last_device_fingerprint IS NULL OR "
        "length(last_device_fingerprint) BETWEEN 1 AND 128",
    )


def downgrade() -> None:
    """Reverse the schema change when it is proven safe."""
    op.drop_constraint(
        op.f("ck_identity_refresh_sessions_last_device_fingerprint_length"),
        "identity_refresh_sessions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_identity_refresh_sessions_last_asn_range"),
        "identity_refresh_sessions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_identity_refresh_sessions_last_country_iso_alpha2"),
        "identity_refresh_sessions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_identity_refresh_sessions_risk_score_range"),
        "identity_refresh_sessions",
        type_="check",
    )
    op.drop_column("identity_refresh_sessions", "last_device_fingerprint")
    op.drop_column("identity_refresh_sessions", "last_asn")
    op.drop_column("identity_refresh_sessions", "last_country")
    op.drop_column("identity_refresh_sessions", "risk_score")
