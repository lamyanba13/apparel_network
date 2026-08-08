"""harden the commerce event outbox

Revision ID: ee6a8b0d2f35
Revises: dd5f7a9c1e24
Create Date: 2026-08-08 00:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ee6a8b0d2f35"
down_revision: str | Sequence[str] | None = "dd5f7a9c1e24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "event_outbox",
        "status",
        existing_type=sa.String(length=9),
        type_=sa.String(length=10),
        existing_nullable=False,
        existing_server_default="pending",
    )
    op.add_column(
        "event_outbox",
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "event_outbox",
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "event_outbox",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "event_outbox", sa.Column("locked_by", sa.String(length=150), nullable=True)
    )
    op.add_column(
        "event_outbox",
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "event_outbox",
        sa.Column("last_error", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "event_outbox",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "event_outbox",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE event_outbox SET available_at = occurred_at, "
        "created_at = occurred_at, updated_at = occurred_at"
    )
    op.create_check_constraint("attempts_nonnegative", "event_outbox", "attempts >= 0")
    op.create_index(
        "ix_event_outbox_available", "event_outbox", ["status", "available_at"]
    )
    op.create_index(
        "ix_event_outbox_stale_lock", "event_outbox", ["status", "locked_at"]
    )
    op.create_table(
        "event_consumer_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("consumer_name", sa.String(length=150), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["event_id"], ["event_outbox.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "consumer_name",
            name="uq_event_consumer_receipts_event_consumer",
        ),
    )
    op.create_index(
        "ix_event_consumer_receipts_event",
        "event_consumer_receipts",
        ["event_id"],
    )
    op.create_index(
        "ix_event_consumer_receipts_consumer",
        "event_consumer_receipts",
        ["consumer_name", "processed_at"],
    )


def downgrade() -> None:
    op.drop_table("event_consumer_receipts")
    op.drop_index("ix_event_outbox_stale_lock", table_name="event_outbox")
    op.drop_index("ix_event_outbox_available", table_name="event_outbox")
    op.drop_constraint("attempts_nonnegative", "event_outbox", type_="check")
    for column in (
        "updated_at",
        "created_at",
        "last_error",
        "dispatched_at",
        "locked_by",
        "locked_at",
        "attempts",
        "available_at",
    ):
        op.drop_column("event_outbox", column)
    op.execute(
        "UPDATE event_outbox SET status = CASE "
        "WHEN status = 'processing' THEN 'pending' "
        "WHEN status = 'dispatched' THEN 'published' ELSE status END"
    )
    op.alter_column(
        "event_outbox",
        "status",
        existing_type=sa.String(length=10),
        type_=sa.String(length=9),
        existing_nullable=False,
        existing_server_default="pending",
    )
