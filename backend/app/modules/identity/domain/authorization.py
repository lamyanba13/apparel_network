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
    PRICE_LIST_CREATE = "price:list:create"
    PRICE_LIST_VIEW = "price:list:view"
    PRICE_LIST_UPDATE = "price:list:update"
    PRICE_RESOLVE = "price:resolve"
    ATTRIBUTE_CREATE = "attribute:create"
    ATTRIBUTE_VIEW = "attribute:view"
    ATTRIBUTE_UPDATE = "attribute:update"
    ATTRIBUTE_ASSIGN = "attribute:assign"
    CART_CREATE = "cart:create"
    CART_VIEW = "cart:view"
    CART_UPDATE = "cart:update"
    CART_DELETE = "cart:delete"
    CHECKOUT_CREATE = "checkout:create"
    CHECKOUT_VIEW = "checkout:view"
    CHECKOUT_UPDATE = "checkout:update"
    CHECKOUT_CONFIRM = "checkout:confirm"
    ORDER_CREATE = "order:create"
    ORDER_VIEW = "order:view"
    ORDER_UPDATE = "order:update"
    ORDER_CONFIRM = "order:confirm"
    PAYMENT_CREATE = "payment:create"
    PAYMENT_VIEW = "payment:view"
    PAYMENT_UPDATE = "payment:update"
    PAYMENT_CAPTURE = "payment:capture"
    PAYMENT_CANCEL = "payment:cancel"
    RESERVATION_CREATE = "reservation:create"
    RESERVATION_VIEW = "reservation:view"
    RESERVATION_UPDATE = "reservation:update"
    RESERVATION_CONSUME = "reservation:consume"
    RESERVATION_RELEASE = "reservation:release"
    RESERVATION_CANCEL = "reservation:cancel"
    SHIPMENT_CREATE = "shipment:create"
    SHIPMENT_VIEW = "shipment:view"
    SHIPMENT_UPDATE = "shipment:update"
    SHIPMENT_SHIP = "shipment:ship"
    SHIPMENT_DELIVER = "shipment:deliver"
    RETURN_CREATE = "return:create"
    RETURN_VIEW = "return:view"
    RETURN_UPDATE = "return:update"
    RETURN_APPROVE = "return:approve"
    RETURN_RECEIVE = "return:receive"
    RETURN_INSPECT = "return:inspect"
    RETURN_REJECT = "return:reject"
    REFUND_CREATE = "refund:create"
    REFUND_VIEW = "refund:view"
    REFUND_PROCESS = "refund:process"
    PROMOTION_CREATE = "promotion:create"
    PROMOTION_VIEW = "promotion:view"
    PROMOTION_UPDATE = "promotion:update"
    PROMOTION_ACTIVATE = "promotion:activate"
    PROMOTION_ARCHIVE = "promotion:archive"
    COUPON_CREATE = "coupon:create"
    COUPON_VIEW = "coupon:view"
    COUPON_UPDATE = "coupon:update"
    COUPON_REDEEM = "coupon:redeem"
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
        segments = normalized.split(":")
        if len(segments) < 2:
            raise ValueError("permission must use resource:action format")
        resource, action = ":".join(segments[:-1]), segments[-1]
        if not all(_SEGMENT_PATTERN.fullmatch(segment) for segment in segments[:-1]):
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
