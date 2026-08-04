"""create payments

Revision ID: 8f0a2b4c6d79
Revises: 7e9f1a3b5d68
Create Date: 2026-08-04 16:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8f0a2b4c6d79"
down_revision: str | Sequence[str] | None = "7e9f1a3b5d68"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "payment:create": UUID("22000000-0000-7000-8000-000000000037"),
    "payment:view": UUID("22000000-0000-7000-8000-000000000038"),
    "payment:update": UUID("22000000-0000-7000-8000-000000000039"),
    "payment:capture": UUID("22000000-0000-7000-8000-000000000040"),
    "payment:cancel": UUID("22000000-0000-7000-8000-000000000041"),
}
ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "admin": UUID("21000000-0000-7000-8000-000000000002"),
    "store_owner": UUID("21000000-0000-7000-8000-000000000003"),
    "store_staff": UUID("21000000-0000-7000-8000-000000000004"),
    "customer": UUID("21000000-0000-7000-8000-000000000005"),
}


def upgrade() -> None:
    op.create_table(
        "payment_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Enum("null", native_enum=False), nullable=False),
        sa.Column("provider_reference", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "created",
                "authorized",
                "captured",
                "failed",
                "cancelled",
                native_enum=False,
            ),
            server_default="created",
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("char_length(currency) = 3", name="currency_length"),
        sa.CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        sa.CheckConstraint("amount >= 0", name="amount_nonnegative"),
        sa.CheckConstraint(
            "char_length(idempotency_key) BETWEEN 16 AND 128",
            name="idempotency_key_length",
        ),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "(status = 'created' AND authorized_at IS NULL AND captured_at IS NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'authorized' AND authorized_at IS NOT NULL "
            "AND captured_at IS NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'captured' AND authorized_at IS NOT NULL "
            "AND captured_at IS NOT NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'failed' AND captured_at IS NULL AND failed_at IS NOT NULL "
            "AND cancelled_at IS NULL AND deleted_at IS NULL) OR "
            "(status = 'cancelled' AND captured_at IS NULL AND failed_at IS NULL "
            "AND cancelled_at IS NOT NULL AND deleted_at IS NOT NULL)",
            name="lifecycle_timestamps",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "customer_id", "idempotency_key", name="uq_payment_intents_idempotency"
        ),
        sa.UniqueConstraint(
            "provider", "provider_reference", name="uq_payment_intents_provider_ref"
        ),
    )
    for name, columns in (
        ("ix_payment_intents_order", ["order_id"]),
        ("ix_payment_intents_customer", ["customer_id"]),
        ("ix_payment_intents_store", ["store_id"]),
        ("ix_payment_intents_status", ["status"]),
        ("ix_payment_intents_expires_at", ["expires_at"]),
    ):
        op.create_index(name, "payment_intents", columns)

    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_intent_id", sa.Uuid(), nullable=False),
        sa.Column("provider_transaction_id", sa.String(length=255), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "created",
                "authorized",
                "captured",
                "failed",
                "cancelled",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "created",
                "authorized",
                "captured",
                "failed",
                "cancelled",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "provider_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("char_length(currency) = 3", name="currency_length"),
        sa.CheckConstraint("currency = upper(currency)", name="currency_uppercase"),
        sa.CheckConstraint("amount >= 0", name="amount_nonnegative"),
        sa.CheckConstraint("event_type = status", name="event_matches_status"),
        sa.ForeignKeyConstraint(
            ["payment_intent_id"], ["payment_intents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_transaction_id", name="uq_payment_transactions_provider_id"
        ),
    )
    op.create_index(
        "ix_payment_transactions_intent",
        "payment_transactions",
        ["payment_intent_id"],
    )
    op.create_index(
        "ix_payment_transactions_occurred_at",
        "payment_transactions",
        ["occurred_at"],
    )
    _seed_permissions()


def downgrade() -> None:
    _remove_permissions()
    op.drop_index(
        "ix_payment_transactions_occurred_at", table_name="payment_transactions"
    )
    op.drop_index("ix_payment_transactions_intent", table_name="payment_transactions")
    op.drop_table("payment_transactions")
    for name in (
        "ix_payment_intents_expires_at",
        "ix_payment_intents_status",
        "ix_payment_intents_store",
        "ix_payment_intents_customer",
        "ix_payment_intents_order",
    ):
        op.drop_index(name, table_name="payment_intents")
    op.drop_table("payment_intents")


def _seed_permissions() -> None:
    permissions = sa.table(
        "identity_permissions",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("resource", sa.String()),
        sa.column("action", sa.String()),
    )
    role_permissions = sa.table(
        "identity_role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
    )
    op.bulk_insert(
        permissions,
        [
            {
                "id": permission_id,
                "name": name,
                "description": f"Payment permission for {name}.",
                "resource": "payment",
                "action": name.split(":", maxsplit=1)[1],
            }
            for name, permission_id in PERMISSIONS.items()
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_id, "permission_id": permission_id}
            for role_id in ROLE_IDS.values()
            for permission_id in PERMISSIONS.values()
        ],
    )


def _remove_permissions() -> None:
    bind = op.get_bind()
    ids = tuple(PERMISSIONS.values())
    role_permissions = sa.table(
        "identity_role_permissions", sa.column("permission_id", sa.Uuid())
    )
    permissions = sa.table("identity_permissions", sa.column("id", sa.Uuid()))
    bind.execute(
        sa.delete(role_permissions).where(role_permissions.c.permission_id.in_(ids))
    )
    bind.execute(sa.delete(permissions).where(permissions.c.id.in_(ids)))
