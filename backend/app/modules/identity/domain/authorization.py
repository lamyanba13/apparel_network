from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

_SEGMENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
_ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,99}$")


class PermissionName(StrEnum):
    """Typed names for the reviewed foundational permission vocabulary."""

    STORE_CREATE = "store:create"
    STORE_VIEW = "store:view"
    STORE_UPDATE = "store:update"
    STORE_DELETE = "store:delete"
    CATALOG_CREATE = "catalog:create"
    CATALOG_UPDATE = "catalog:update"
    CATALOG_VIEW = "catalog:view"
    INVENTORY_VIEW = "inventory:view"
    INVENTORY_UPDATE = "inventory:update"
    PRICE_CREATE = "price:create"
    PRICE_VIEW = "price:view"
    PRICE_UPDATE = "price:update"
    RESERVATION_CREATE = "reservation:create"
    RESERVATION_CANCEL = "reservation:cancel"
    ADMIN_ACCESS = "admin:access"
    SYSTEM_MANAGE = "system:manage"


@dataclass(frozen=True, slots=True)
class Permission:
    resource: str
    action: str

    @property
    def name(self) -> str:
        return f"{self.resource}:{self.action}"


@dataclass(frozen=True, slots=True)
class AuthorizationPrincipal:
    user_id: UUID
    session_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AuthorizationSnapshot:
    roles: frozenset[str]
    permissions: frozenset[str]


class PermissionRegistry:
    """Validate identifiers and expose typed names without defining grants."""

    def parse(self, value: str | PermissionName) -> Permission:
        normalized = value.strip()
        if normalized.count(":") != 1:
            raise ValueError("permission must use resource:action format")
        resource, action = normalized.split(":", maxsplit=1)
        if not _SEGMENT_PATTERN.fullmatch(resource):
            raise ValueError("permission resource must be lowercase snake_case")
        if not _SEGMENT_PATTERN.fullmatch(action):
            raise ValueError("permission action must be lowercase snake_case")
        return Permission(resource=resource, action=action)

    def validate_role(self, value: str) -> str:
        normalized = value.strip()
        if not _ROLE_PATTERN.fullmatch(normalized):
            raise ValueError("role must be lowercase snake_case")
        return normalized

    @staticmethod
    def foundational() -> tuple[PermissionName, ...]:
        return tuple(PermissionName)
