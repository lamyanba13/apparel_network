"""seed authorization foundation

Revision ID: f25a7c19e4d0
Revises: d41f63a709b2
Create Date: 2026-07-30 18:00:00+00:00
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "f25a7c19e4d0"
down_revision: str | Sequence[str] | None = "d41f63a709b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_IDS = {
    "super_admin": UUID("21000000-0000-7000-8000-000000000001"),
    "admin": UUID("21000000-0000-7000-8000-000000000002"),
    "store_owner": UUID("21000000-0000-7000-8000-000000000003"),
    "store_staff": UUID("21000000-0000-7000-8000-000000000004"),
    "customer": UUID("21000000-0000-7000-8000-000000000005"),
    "guest": UUID("21000000-0000-7000-8000-000000000006"),
}
PERMISSION_NAMES = (
    "store:create",
    "store:view",
    "store:update",
    "store:delete",
    "catalog:create",
    "catalog:update",
    "catalog:view",
    "inventory:view",
    "inventory:update",
    "reservation:create",
    "reservation:cancel",
    "admin:access",
    "system:manage",
)
PERMISSION_IDS = {
    name: UUID(f"22000000-0000-7000-8000-{index:012d}")
    for index, name in enumerate(PERMISSION_NAMES, start=1)
}
GRANTS = {
    "super_admin": set(PERMISSION_NAMES),
    "admin": {"admin:access"},
    "store_owner": {
        "store:view",
        "store:update",
        "catalog:create",
        "catalog:update",
        "catalog:view",
        "inventory:view",
        "inventory:update",
    },
    "store_staff": {
        "catalog:update",
        "catalog:view",
        "inventory:view",
        "inventory:update",
    },
    "customer": {
        "store:view",
        "catalog:view",
        "inventory:view",
        "reservation:create",
        "reservation:cancel",
    },
    "guest": {"store:view", "catalog:view", "inventory:view"},
}


def upgrade() -> None:
    """Add canonical identifier constraints and immutable default RBAC data."""
    op.create_check_constraint(
        "name_canonical",
        "identity_roles",
        "name ~ '^[a-z][a-z0-9_]{0,99}$'",
    )
    op.create_check_constraint(
        "resource_canonical",
        "identity_permissions",
        "resource ~ '^[a-z][a-z0-9_]{0,99}$'",
    )
    op.create_check_constraint(
        "action_canonical",
        "identity_permissions",
        "action ~ '^[a-z][a-z0-9_]{0,99}$'",
    )
    op.create_check_constraint(
        "name_matches_resource_action",
        "identity_permissions",
        "name = resource || ':' || action",
    )

    roles = sa.table(
        "identity_roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("is_system", sa.Boolean()),
        sa.column("is_immutable", sa.Boolean()),
    )
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
    labels = {
        "super_admin": "Super Administrator",
        "admin": "Administrator",
        "store_owner": "Store Owner",
        "store_staff": "Store Staff",
        "customer": "Customer",
        "guest": "Guest",
    }
    op.bulk_insert(
        roles,
        [
            {
                "id": role_id,
                "name": name,
                "description": f"System role: {labels[name]}",
                "is_system": True,
                "is_immutable": True,
            }
            for name, role_id in ROLE_IDS.items()
        ],
    )
    op.bulk_insert(
        permissions,
        [
            {
                "id": permission_id,
                "name": name,
                "description": f"Candidate permission for {name}.",
                "resource": name.split(":", maxsplit=1)[0],
                "action": name.split(":", maxsplit=1)[1],
            }
            for name, permission_id in PERMISSION_IDS.items()
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            {
                "role_id": ROLE_IDS[role],
                "permission_id": PERMISSION_IDS[permission],
            }
            for role, grants in GRANTS.items()
            for permission in sorted(grants)
        ],
    )


def downgrade() -> None:
    """Remove only the Phase 2.4 seed data and constraints."""
    bind = op.get_bind()
    role_permissions = sa.table(
        "identity_role_permissions",
        sa.column("role_id", sa.Uuid()),
    )
    permissions = sa.table(
        "identity_permissions",
        sa.column("id", sa.Uuid()),
    )
    roles = sa.table("identity_roles", sa.column("id", sa.Uuid()))
    bind.execute(
        sa.delete(role_permissions).where(
            role_permissions.c.role_id.in_(tuple(ROLE_IDS.values()))
        )
    )
    bind.execute(
        sa.delete(permissions).where(
            permissions.c.id.in_(tuple(PERMISSION_IDS.values()))
        )
    )
    bind.execute(sa.delete(roles).where(roles.c.id.in_(tuple(ROLE_IDS.values()))))
    op.drop_constraint(
        "ck_identity_permissions_name_matches_resource_action",
        "identity_permissions",
        type_="check",
    )
    op.drop_constraint(
        "ck_identity_permissions_action_canonical",
        "identity_permissions",
        type_="check",
    )
    op.drop_constraint(
        "ck_identity_permissions_resource_canonical",
        "identity_permissions",
        type_="check",
    )
    op.drop_constraint(
        "ck_identity_roles_name_canonical",
        "identity_roles",
        type_="check",
    )
