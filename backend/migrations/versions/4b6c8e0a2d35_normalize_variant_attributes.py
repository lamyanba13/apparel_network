"""normalize variant attributes

Revision ID: 4b6c8e0a2d35
Revises: 3a5b7d9f1c24
Create Date: 2026-08-03 23:00:00+00:00
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from uuid6 import uuid7

revision: str = "4b6c8e0a2d35"
down_revision: str | Sequence[str] | None = "3a5b7d9f1c24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "attribute:create": UUID("22000000-0000-7000-8000-000000000021"),
    "attribute:view": UUID("22000000-0000-7000-8000-000000000022"),
    "attribute:update": UUID("22000000-0000-7000-8000-000000000023"),
    "attribute:assign": UUID("22000000-0000-7000-8000-000000000024"),
}
ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "store_owner": UUID("21000000-0000-7000-8000-000000000003"),
    "store_staff": UUID("21000000-0000-7000-8000-000000000004"),
}
GRANTS = {
    "super_admin": set(PERMISSIONS),
    "store_owner": set(PERMISSIONS),
    "store_staff": {"attribute:view", "attribute:update", "attribute:assign"},
}


def upgrade() -> None:
    op.create_table(
        "product_attributes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "text",
                "number",
                "boolean",
                "date",
                "color",
                "size",
                "enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("filterable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("searchable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "archived", native_enum=False),
            server_default="active",
            nullable=False,
        ),
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
        sa.CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "deleted_at IS NULL OR status = 'archived'", name="deleted_archived"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id", "slug", name="uq_product_attributes_store_slug"
        ),
    )
    for name, columns in (
        ("ix_product_attributes_store", ["store_id"]),
        ("ix_product_attributes_status", ["status"]),
        ("ix_product_attributes_type", ["type"]),
        ("ix_product_attributes_order", ["store_id", "sort_order"]),
    ):
        op.create_index(name, "product_attributes", columns)

    op.create_table(
        "product_attribute_values",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attribute_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
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
        sa.CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["attribute_id"], ["product_attributes.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attribute_id",
            "slug",
            name="uq_product_attribute_values_attribute_slug",
        ),
    )
    op.create_index(
        "ix_product_attribute_values_attribute",
        "product_attribute_values",
        ["attribute_id"],
    )
    op.create_index(
        "ix_product_attribute_values_order",
        "product_attribute_values",
        ["attribute_id", "sort_order"],
    )

    op.create_table(
        "product_variant_attribute_values",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("attribute_value_id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["product_variants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["attribute_value_id"],
            ["product_attribute_values.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "variant_id",
            "attribute_value_id",
            name="uq_product_variant_attribute_values_variant_value",
        ),
    )
    op.create_index(
        "ix_product_variant_attribute_values_variant",
        "product_variant_attribute_values",
        ["variant_id"],
    )
    op.create_index(
        "ix_product_variant_attribute_values_value",
        "product_variant_attribute_values",
        ["attribute_value_id"],
    )

    op.create_table(
        "event_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("event_name", sa.String(length=150), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "published", "failed", native_enum=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_outbox_status", "event_outbox", ["status"])
    op.create_index("ix_event_outbox_occurred_at", "event_outbox", ["occurred_at"])
    op.create_index(
        "ix_event_outbox_aggregate_type", "event_outbox", ["aggregate_type"]
    )

    _backfill_normalized_attributes()
    op.drop_column("product_variants", "attributes")
    _seed_permissions()


def downgrade() -> None:
    op.add_column("product_variants", sa.Column("attributes", JSONB(), nullable=True))
    _restore_json_attributes()
    op.alter_column("product_variants", "attributes", nullable=False)
    _remove_permissions()

    for name in (
        "ix_event_outbox_aggregate_type",
        "ix_event_outbox_occurred_at",
        "ix_event_outbox_status",
    ):
        op.drop_index(name, table_name="event_outbox")
    op.drop_table("event_outbox")
    op.drop_index(
        "ix_product_variant_attribute_values_value",
        table_name="product_variant_attribute_values",
    )
    op.drop_index(
        "ix_product_variant_attribute_values_variant",
        table_name="product_variant_attribute_values",
    )
    op.drop_table("product_variant_attribute_values")
    op.drop_index(
        "ix_product_attribute_values_order", table_name="product_attribute_values"
    )
    op.drop_index(
        "ix_product_attribute_values_attribute",
        table_name="product_attribute_values",
    )
    op.drop_table("product_attribute_values")
    for name in (
        "ix_product_attributes_order",
        "ix_product_attributes_type",
        "ix_product_attributes_status",
        "ix_product_attributes_store",
    ):
        op.drop_index(name, table_name="product_attributes")
    op.drop_table("product_attributes")


def _backfill_normalized_attributes() -> None:
    bind = op.get_bind()
    variants = bind.execute(
        sa.text(
            "SELECT id, store_id, attributes FROM product_variants "
            "ORDER BY store_id, id"
        )
    ).mappings()
    attribute_ids: dict[tuple[UUID, str], UUID] = {}
    attribute_slugs: dict[tuple[UUID, str], str] = {}
    value_ids: dict[tuple[UUID, str], UUID] = {}
    value_slugs: dict[tuple[UUID, str], str] = {}
    for variant in variants:
        assigned_ids: list[UUID] = []
        attributes = variant["attributes"] or {}
        for order, (name, value) in enumerate(sorted(attributes.items())):
            store_id = variant["store_id"]
            attribute_key = (store_id, name)
            attribute_id = attribute_ids.get(attribute_key)
            if attribute_id is None:
                attribute_id = uuid7()
                attribute_slug = _unique_slug(
                    name,
                    {
                        slug
                        for (candidate_store, _), slug in attribute_slugs.items()
                        if candidate_store == store_id
                    },
                )
                attribute_ids[attribute_key] = attribute_id
                attribute_slugs[attribute_key] = attribute_slug
                bind.execute(
                    sa.text(
                        "INSERT INTO product_attributes "
                        "(id, store_id, name, slug, type, required, filterable, "
                        "searchable, sort_order, status, version) VALUES "
                        "(:id, :store_id, :name, :slug, 'enum', false, true, "
                        "true, :sort_order, 'active', 1)"
                    ),
                    {
                        "id": attribute_id,
                        "store_id": store_id,
                        "name": name,
                        "slug": attribute_slug,
                        "sort_order": order,
                    },
                )
            value_key = (attribute_id, value)
            value_id = value_ids.get(value_key)
            if value_id is None:
                value_id = uuid7()
                value_slug = _unique_slug(
                    value,
                    {
                        slug
                        for (candidate_attribute, _), slug in value_slugs.items()
                        if candidate_attribute == attribute_id
                    },
                )
                value_ids[value_key] = value_id
                value_slugs[value_key] = value_slug
                bind.execute(
                    sa.text(
                        "INSERT INTO product_attribute_values "
                        "(id, attribute_id, value, slug, sort_order, version) "
                        "VALUES (:id, :attribute_id, :value, :slug, 0, 1)"
                    ),
                    {
                        "id": value_id,
                        "attribute_id": attribute_id,
                        "value": value,
                        "slug": value_slug,
                    },
                )
            assigned_ids.append(value_id)
            bind.execute(
                sa.text(
                    "INSERT INTO product_variant_attribute_values "
                    "(id, variant_id, attribute_value_id, version) "
                    "VALUES (:id, :variant_id, :value_id, 1)"
                ),
                {"id": uuid7(), "variant_id": variant["id"], "value_id": value_id},
            )
        bind.execute(
            sa.text(
                "UPDATE product_variants SET attribute_signature = :signature "
                "WHERE id = :variant_id"
            ),
            {
                "signature": _normalized_signature(assigned_ids),
                "variant_id": variant["id"],
            },
        )


def _restore_json_attributes() -> None:
    bind = op.get_bind()
    variants = bind.execute(sa.text("SELECT id FROM product_variants ORDER BY id"))
    for (variant_id,) in variants:
        rows = bind.execute(
            sa.text(
                "SELECT pa.name, pav.value "
                "FROM product_variant_attribute_values pvav "
                "JOIN product_attribute_values pav "
                "ON pav.id = pvav.attribute_value_id "
                "JOIN product_attributes pa ON pa.id = pav.attribute_id "
                "WHERE pvav.variant_id = :variant_id ORDER BY pa.slug, pav.slug"
            ),
            {"variant_id": variant_id},
        )
        attributes = {name.casefold(): value for name, value in rows}
        canonical = json.dumps(
            attributes, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        bind.execute(
            sa.text(
                "UPDATE product_variants SET attributes = CAST(:attributes AS jsonb), "
                "attribute_signature = :signature WHERE id = :variant_id"
            ),
            {
                "attributes": canonical,
                "signature": hashlib.sha256(canonical.encode()).hexdigest(),
                "variant_id": variant_id,
            },
        )


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
                "description": f"Variant Attribute permission for {name}.",
                "resource": "attribute",
                "action": name.split(":", maxsplit=1)[1],
            }
            for name, permission_id in PERMISSIONS.items()
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": ROLE_IDS[role], "permission_id": PERMISSIONS[permission]}
            for role, grants in GRANTS.items()
            for permission in sorted(grants)
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


def _normalized_signature(value_ids: Sequence[UUID]) -> str:
    canonical = json.dumps(sorted(str(value_id) for value_id in value_ids))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _unique_slug(value: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "value"
    base = base[:180]
    if base not in existing:
        return base
    suffix = hashlib.sha256(value.encode()).hexdigest()[:8]
    return f"{base[:171]}-{suffix}"
