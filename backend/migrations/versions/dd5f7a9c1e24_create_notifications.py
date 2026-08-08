"""create customer notifications and commerce event delivery

Revision ID: dd5f7a9c1e24
Revises: cc4e6f8a0b13
Create Date: 2026-08-05 00:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dd5f7a9c1e24"
down_revision: str | Sequence[str] | None = "cc4e6f8a0b13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "notification:view": UUID("22000000-0000-7000-8000-000000000070"),
    "notification:update": UUID("22000000-0000-7000-8000-000000000071"),
    "notification:test": UUID("22000000-0000-7000-8000-000000000072"),
    "notification:preferences": UUID("22000000-0000-7000-8000-000000000073"),
}
ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "admin": UUID("21000000-0000-7000-8000-000000000002"),
    "customer": UUID("21000000-0000-7000-8000-000000000005"),
}
CHANNELS = ("email", "sms", "push", "in_app")
STATUSES = (
    "pending",
    "queued",
    "sending",
    "delivered",
    "failed",
    "retrying",
    "cancelled",
)
TEMPLATES: tuple[tuple[str, str, str, str, list[str]], ...] = (
    (
        "order_created",
        "order.created",
        "Order received",
        "Order $order_id was received.",
        ["order_id"],
    ),
    (
        "order_confirmation",
        "order.confirmed",
        "Order confirmed",
        "Order $order_id is confirmed.",
        ["order_id"],
    ),
    (
        "payment_authorized",
        "payment.created",
        "Payment started",
        "Payment $payment_id was created for order $order_id.",
        ["payment_id", "order_id"],
    ),
    (
        "payment_captured",
        "payment.captured",
        "Payment captured",
        "Payment $payment_id was captured.",
        ["payment_id"],
    ),
    (
        "shipment_created",
        "shipment.created",
        "Shipment created",
        "Shipment $shipment_id was created.",
        ["shipment_id"],
    ),
    (
        "shipment_packed",
        "shipment.packed",
        "Shipment packed",
        "Shipment $shipment_id was packed.",
        ["shipment_id"],
    ),
    (
        "shipment_shipped",
        "shipment.shipped",
        "Shipment shipped",
        "Shipment $shipment_id has shipped.",
        ["shipment_id"],
    ),
    (
        "shipment_delivered",
        "shipment.delivered",
        "Shipment delivered",
        "Shipment $shipment_id was delivered.",
        ["shipment_id"],
    ),
    (
        "return_approved",
        "return.approved",
        "Return approved",
        "Return $return_id was approved.",
        ["return_id"],
    ),
    (
        "refund_completed",
        "refund.completed",
        "Refund completed",
        "Refund $refund_id was completed.",
        ["refund_id"],
    ),
    (
        "promotion_applied",
        "promotion.applied",
        "Promotion applied",
        "Promotion $promotion_id was applied.",
        ["promotion_id"],
    ),
    (
        "coupon_redeemed",
        "coupon.redeemed",
        "Coupon redeemed",
        "Coupon $coupon_id was redeemed.",
        ["coupon_id"],
    ),
    (
        "notification_test",
        "notification.test",
        "Test notification",
        "This is a test notification.",
        [],
    ),
)


def _lifecycle_columns() -> list[sa.Column[Any]]:
    return [
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
        sa.Column("created_by_id", sa.Uuid()),
        sa.Column("updated_by_id", sa.Uuid()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    ]


def upgrade() -> None:
    op.create_table(
        "notification_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("event_name", sa.String(100), nullable=False),
        sa.Column("channel", sa.Enum(*CHANNELS, native_enum=False), nullable=False),
        sa.Column("language", sa.String(10), server_default="en", nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "variables",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        *_lifecycle_columns(),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_name",
            "channel",
            "language",
            name="uq_notification_templates_event_channel_language",
        ),
    )
    op.create_index(
        "ix_notification_templates_lookup",
        "notification_templates",
        ["event_name", "channel", "language", "active"],
    )
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sms_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("push_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "in_app_enabled", sa.Boolean(), server_default="true", nullable=False
        ),
        sa.Column("language", sa.String(10), server_default="en", nullable=False),
        sa.Column(
            "marketing_opt_in", sa.Boolean(), server_default="false", nullable=False
        ),
        *_lifecycle_columns(),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["identity_users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id", name="uq_notification_preferences_customer"),
    )
    op.create_index(
        "ix_notification_preferences_customer",
        "notification_preferences",
        ["customer_id"],
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid()),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("source_event_id", sa.Uuid()),
        sa.Column("event_name", sa.String(100), nullable=False),
        sa.Column("channel", sa.Enum(*CHANNELS, native_enum=False), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*STATUSES, native_enum=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "variables",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("queued_at", sa.DateTime(timezone=True)),
        sa.Column("sending_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        *_lifecycle_columns(),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        sa.CheckConstraint("max_retries >= 0", name="max_retries_non_negative"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["identity_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["template_id"], ["notification_templates.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_event_id"], ["event_outbox.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_event_id",
            "customer_id",
            "channel",
            name="uq_notifications_source_customer_channel",
        ),
    )
    for name, columns in (
        ("ix_notifications_customer_status", ["customer_id", "status"]),
        ("ix_notifications_store", ["store_id"]),
        ("ix_notifications_retry", ["status", "next_retry_at"]),
        ("ix_notifications_source_event", ["source_event_id"]),
    ):
        op.create_index(name, "notifications", columns)
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Enum(*CHANNELS, native_enum=False), nullable=False),
        sa.Column("gateway_reference", sa.String(100), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        *_lifecycle_columns(),
        sa.CheckConstraint("duration_ms >= 0", name="duration_ms_non_negative"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_id", name="uq_notification_deliveries_notification"
        ),
    )
    op.create_index(
        "ix_notification_deliveries_notification",
        "notification_deliveries",
        ["notification_id"],
    )
    op.create_table(
        "notification_failures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=False),
        sa.Column("retry_at", sa.DateTime(timezone=True)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *_lifecycle_columns(),
        sa.CheckConstraint("attempt > 0", name="attempt_positive"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_id", "attempt", name="uq_notification_failures_attempt"
        ),
    )
    op.create_index(
        "ix_notification_failures_notification",
        "notification_failures",
        ["notification_id"],
    )
    _seed_templates()
    _seed_permissions()


def downgrade() -> None:
    _remove_permissions()
    op.drop_table("notification_failures")
    op.drop_table("notification_deliveries")
    op.drop_table("notifications")
    op.drop_table("notification_preferences")
    op.drop_table("notification_templates")


def _seed_templates() -> None:
    table = sa.table(
        "notification_templates",
        sa.column("id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("event_name", sa.String()),
        sa.column("channel", sa.String()),
        sa.column("language", sa.String()),
        sa.column("subject", sa.String()),
        sa.column("body", sa.Text()),
        sa.column("variables", postgresql.JSONB()),
        sa.column("active", sa.Boolean()),
    )
    rows = []
    sequence = 1
    for key, event_name, subject, body, variables in TEMPLATES:
        for channel in CHANNELS:
            rows.append(
                {
                    "id": UUID(f"25000000-0000-7000-8000-{sequence:012d}"),
                    "key": key,
                    "event_name": event_name,
                    "channel": channel,
                    "language": "en",
                    "subject": subject,
                    "body": body,
                    "variables": variables,
                    "active": True,
                }
            )
            sequence += 1
    op.bulk_insert(table, rows)


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
                "description": f"Notification permission for {name}.",
                "resource": "notification",
                "action": name.split(":", 1)[1],
            }
            for name, permission_id in PERMISSIONS.items()
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_id, "permission_id": permission_id}
            for role_name, role_id in ROLE_IDS.items()
            for name, permission_id in PERMISSIONS.items()
            if role_name != "customer" or name != "notification:test"
        ],
    )


def _remove_permissions() -> None:
    bind = op.get_bind()
    permission_ids = tuple(PERMISSIONS.values())
    role_permissions = sa.table(
        "identity_role_permissions", sa.column("permission_id", sa.Uuid())
    )
    permissions = sa.table("identity_permissions", sa.column("id", sa.Uuid()))
    bind.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.permission_id.in_(permission_ids)
        )
    )
    bind.execute(sa.delete(permissions).where(permissions.c.id.in_(permission_ids)))
