from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from app.modules.identity.domain.authorization import (
    AuthorizationPrincipal,
    PermissionName,
    PermissionRegistry,
)


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    """Extensible, read-only input supplied to a resource-owned policy."""

    principal: AuthorizationPrincipal
    resource: object | None
    action: str | PermissionName
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action",
            PermissionRegistry().parse(self.action).name,
        )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )


class PolicyOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"


class PolicyDecisionReason(StrEnum):
    ALLOWED = "allowed"
    POLICY_DENIED = "policy_denied"
    MISSING_PERMISSION = "missing_permission"
    POLICY_NOT_IMPLEMENTED = "policy_not_implemented"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Internal decision detail; clients still receive generic denials."""

    outcome: PolicyOutcome
    reason: PolicyDecisionReason
    policy: str
    missing_permission: str | None = None

    def __post_init__(self) -> None:
        if not self.policy.strip():
            raise ValueError("policy name is required")
        if self.missing_permission is not None:
            object.__setattr__(
                self,
                "missing_permission",
                PermissionRegistry().parse(self.missing_permission).name,
            )
        if self.outcome is PolicyOutcome.ALLOWED:
            if (
                self.reason is not PolicyDecisionReason.ALLOWED
                or self.missing_permission is not None
            ):
                raise ValueError("allowed policy decisions must use allowed reason")
        elif self.reason is PolicyDecisionReason.ALLOWED:
            raise ValueError("denied policy decisions require a denial reason")
        if (self.reason is PolicyDecisionReason.MISSING_PERMISSION) != (
            self.missing_permission is not None
        ):
            raise ValueError(
                "missing permission is required only for that denial reason"
            )

    @property
    def allowed(self) -> bool:
        return self.outcome is PolicyOutcome.ALLOWED

    @classmethod
    def allow(cls, *, policy: str) -> PolicyDecision:
        return cls(
            outcome=PolicyOutcome.ALLOWED,
            reason=PolicyDecisionReason.ALLOWED,
            policy=policy,
        )

    @classmethod
    def deny(
        cls,
        *,
        policy: str,
        reason: PolicyDecisionReason,
        missing_permission: str | None = None,
    ) -> PolicyDecision:
        return cls(
            outcome=PolicyOutcome.DENIED,
            reason=reason,
            policy=policy,
            missing_permission=missing_permission,
        )


class BusinessAuthorizationPolicy(Protocol):
    """Future business-policy port; concrete rules belong to owning modules."""

    async def can_update_store(
        self,
        context: AuthorizationContext,
    ) -> PolicyDecision: ...

    async def can_publish_catalog(
        self,
        context: AuthorizationContext,
    ) -> PolicyDecision: ...

    async def can_delete_inventory(
        self,
        context: AuthorizationContext,
    ) -> PolicyDecision: ...


class DeferredBusinessAuthorizationPolicy:
    """Deny-by-default placeholder until each business module owns its rules."""

    async def can_update_store(
        self,
        context: AuthorizationContext,
    ) -> PolicyDecision:
        return self._denied("can_update_store")

    async def can_publish_catalog(
        self,
        context: AuthorizationContext,
    ) -> PolicyDecision:
        return self._denied("can_publish_catalog")

    async def can_delete_inventory(
        self,
        context: AuthorizationContext,
    ) -> PolicyDecision:
        return self._denied("can_delete_inventory")

    @staticmethod
    def _denied(policy: str) -> PolicyDecision:
        return PolicyDecision.deny(
            policy=policy,
            reason=PolicyDecisionReason.POLICY_NOT_IMPLEMENTED,
        )
