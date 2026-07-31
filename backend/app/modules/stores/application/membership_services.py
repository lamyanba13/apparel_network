from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.common.context import maybe_get_request_context
from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.identity.application.repositories import UserRepository
from app.modules.stores.application.membership_repositories import (
    StoreMembershipRepository,
)
from app.modules.stores.application.membership_schemas import (
    StoreMembershipInvitation,
    StoreMembershipUpdate,
)
from app.modules.stores.application.repositories import StoreRepository
from app.modules.stores.domain import (
    Store,
    StoreMemberAccepted,
    StoreMemberDeclined,
    StoreMemberInvited,
    StoreMemberReactivated,
    StoreMemberRemoved,
    StoreMemberRoleChanged,
    StoreMembership,
    StoreMembershipEvent,
    StoreMembershipRole,
    StoreMembershipStatus,
    StoreMemberSuspended,
)
from app.observability.metrics import (
    STORE_MEMBER_ACCEPTANCES,
    STORE_MEMBER_INVITATIONS,
    STORE_MEMBER_REMOVALS,
    STORE_MEMBERS,
)

INVITATION_LIFETIME = timedelta(days=7)


class MembershipAuditService:
    """Publish safe Store membership lifecycle events."""

    def __init__(self, events: EventPublisher) -> None:
        self._events = events

    async def publish(
        self,
        event_type: type[StoreMembershipEvent],
        membership: StoreMembership,
        actor_user_id: UUID,
    ) -> None:
        await self._events.publish(
            event_type(
                membership_id=membership.id,
                store_id=membership.store_id,
                user_id=membership.user_id,
                actor_user_id=actor_user_id,
                role=membership.role,
                status=membership.status,
                correlation_id=_correlation_id(),
            )
        )


class MembershipLifecycleService:
    """Apply atomic conditional transitions to a membership."""

    def __init__(
        self,
        memberships: StoreMembershipRepository,
        audit: MembershipAuditService,
    ) -> None:
        self._memberships = memberships
        self._audit = audit

    async def accept(
        self,
        membership: StoreMembership,
        actor_user_id: UUID,
        expected_version: int,
    ) -> StoreMembership:
        if membership.user_id != actor_user_id:
            raise _membership_not_found()
        now = datetime.now(UTC)
        if (
            membership.invitation_expires_at is None
            or membership.invitation_expires_at <= now
        ):
            await self._memberships.expire_pending(membership.store_id, now=now)
            raise _conflict("The Store invitation has expired.")
        updated = await self._memberships.transition(
            membership.id,
            from_statuses=frozenset({StoreMembershipStatus.PENDING}),
            status=StoreMembershipStatus.ACTIVE,
            expected_version=expected_version,
            accepted_at=now,
        )
        if updated is None:
            raise _conflict("The membership changed or is not pending.")
        STORE_MEMBER_ACCEPTANCES.inc()
        await self._audit.publish(StoreMemberAccepted, updated, actor_user_id)
        await self._snapshot()
        return updated

    async def decline(
        self,
        membership: StoreMembership,
        actor_user_id: UUID,
        expected_version: int,
    ) -> StoreMembership:
        if membership.user_id != actor_user_id:
            raise _membership_not_found()
        updated = await self._memberships.transition(
            membership.id,
            from_statuses=frozenset({StoreMembershipStatus.PENDING}),
            status=StoreMembershipStatus.DECLINED,
            expected_version=expected_version,
            removed_at=datetime.now(UTC),
        )
        if updated is None:
            raise _conflict("The membership changed or is not pending.")
        await self._audit.publish(StoreMemberDeclined, updated, actor_user_id)
        return updated

    async def suspend_or_reactivate(
        self,
        membership: StoreMembership,
        actor_user_id: UUID,
        target: StoreMembershipStatus,
        expected_version: int,
    ) -> StoreMembership:
        if membership.role is StoreMembershipRole.OWNER:
            raise _conflict("The Store owner membership cannot be changed.")
        transitions = {
            StoreMembershipStatus.SUSPENDED: (
                StoreMembershipStatus.ACTIVE,
                StoreMemberSuspended,
            ),
            StoreMembershipStatus.ACTIVE: (
                StoreMembershipStatus.SUSPENDED,
                StoreMemberReactivated,
            ),
        }
        transition = transitions.get(target)
        if transition is None:
            raise _validation(
                "status",
                "Only active and suspended lifecycle changes are supported.",
            )
        source, event_type = transition
        updated = await self._memberships.transition(
            membership.id,
            from_statuses=frozenset({source}),
            status=target,
            expected_version=expected_version,
        )
        if updated is None:
            raise _conflict("The membership changed or cannot make that transition.")
        await self._audit.publish(event_type, updated, actor_user_id)
        await self._snapshot()
        return updated

    async def remove(
        self,
        membership: StoreMembership,
        actor_user_id: UUID,
    ) -> StoreMembership:
        if membership.role is StoreMembershipRole.OWNER:
            raise _conflict("The Store owner membership cannot be removed.")
        updated = await self._memberships.transition(
            membership.id,
            from_statuses=frozenset(
                {
                    StoreMembershipStatus.PENDING,
                    StoreMembershipStatus.ACTIVE,
                    StoreMembershipStatus.SUSPENDED,
                }
            ),
            status=StoreMembershipStatus.REMOVED,
            expected_version=membership.version,
            removed_at=datetime.now(UTC),
        )
        if updated is None:
            raise _conflict("The membership changed or is already terminal.")
        STORE_MEMBER_REMOVALS.inc()
        await self._audit.publish(StoreMemberRemoved, updated, actor_user_id)
        await self._snapshot()
        return updated

    async def _snapshot(self) -> None:
        STORE_MEMBERS.set(await self._memberships.count_current())

    async def audit_role_change(
        self,
        membership: StoreMembership,
        actor_user_id: UUID,
    ) -> None:
        await self._audit.publish(
            StoreMemberRoleChanged,
            membership,
            actor_user_id,
        )


class StoreInvitationService:
    """Create bounded, non-owner Store invitations."""

    def __init__(
        self,
        memberships: StoreMembershipRepository,
        users: UserRepository,
        audit: MembershipAuditService,
    ) -> None:
        self._memberships = memberships
        self._users = users
        self._audit = audit

    async def invite(
        self,
        store: Store,
        actor_user_id: UUID,
        invitation: StoreMembershipInvitation,
    ) -> StoreMembership:
        if invitation.role is StoreMembershipRole.OWNER:
            raise _validation(
                "role",
                "Owner invitations are not supported; ownership transfer is excluded.",
            )
        if invitation.user_id == store.owner_id:
            raise _conflict("The Store owner already has an active membership.")
        if await self._users.get_by_id(invitation.user_id) is None:
            raise _user_not_found()
        await self._memberships.expire_pending(store.id, now=datetime.now(UTC))
        if await self._memberships.find_open(store.id, invitation.user_id) is not None:
            raise _conflict(
                "An active membership or pending invitation already exists."
            )
        membership = await self._memberships.add_invitation(
            store_id=store.id,
            user_id=invitation.user_id,
            role=invitation.role,
            invited_by_id=actor_user_id,
            expires_at=datetime.now(UTC) + INVITATION_LIFETIME,
        )
        STORE_MEMBER_INVITATIONS.inc()
        await self._audit.publish(StoreMemberInvited, membership, actor_user_id)
        return membership


class StoreMembershipService:
    """Owner-scoped Store membership use cases and invitee responses."""

    def __init__(
        self,
        stores: StoreRepository,
        memberships: StoreMembershipRepository,
        invitations: StoreInvitationService,
        lifecycle: MembershipLifecycleService,
    ) -> None:
        self._stores = stores
        self._memberships = memberships
        self._invitations = invitations
        self._lifecycle = lifecycle

    async def invite(
        self,
        store_id: UUID,
        actor_user_id: UUID,
        invitation: StoreMembershipInvitation,
    ) -> StoreMembership:
        store = await self._owned_store(store_id, actor_user_id)
        await self._ensure_owner(store)
        return await self._invitations.invite(store, actor_user_id, invitation)

    async def list(
        self,
        store_id: UUID,
        actor_user_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[StoreMembership], int]:
        store = await self._owned_store(store_id, actor_user_id)
        await self._ensure_owner(store)
        await self._memberships.expire_pending(store.id, now=datetime.now(UTC))
        return await self._memberships.list_for_store(
            store.id,
            offset=offset,
            limit=limit,
        )

    async def update(
        self,
        store_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
        changes: StoreMembershipUpdate,
    ) -> StoreMembership:
        await self._owned_store(store_id, actor_user_id)
        membership = await self._require_membership(store_id, membership_id)
        if changes.role is None and changes.status is None:
            raise _validation("body", "At least one membership change is required.")
        if changes.role is StoreMembershipRole.OWNER:
            raise _validation(
                "role",
                "Owner assignment is excluded from Store staff management.",
            )
        current = membership
        if changes.role is not None and changes.role != current.role:
            if changes.status is not None:
                raise _validation(
                    "body",
                    "Role and lifecycle changes must be submitted separately.",
                )
            updated = await self._memberships.update_role(
                current.id,
                role=changes.role,
                expected_version=changes.expected_version,
            )
            if updated is None:
                raise _conflict("The membership changed or cannot be updated.")
            await self._lifecycle.audit_role_change(updated, actor_user_id)
            return updated
        if changes.status is not None:
            return await self._lifecycle.suspend_or_reactivate(
                current,
                actor_user_id,
                changes.status,
                changes.expected_version,
            )
        return current

    async def remove(
        self,
        store_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
    ) -> None:
        await self._owned_store(store_id, actor_user_id)
        membership = await self._require_membership(store_id, membership_id)
        await self._lifecycle.remove(membership, actor_user_id)

    async def accept(
        self,
        store_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
        expected_version: int,
    ) -> StoreMembership:
        await self._require_store(store_id)
        membership = await self._require_membership(store_id, membership_id)
        return await self._lifecycle.accept(
            membership,
            actor_user_id,
            expected_version,
        )

    async def decline(
        self,
        store_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
        expected_version: int,
    ) -> StoreMembership:
        await self._require_store(store_id)
        membership = await self._require_membership(store_id, membership_id)
        return await self._lifecycle.decline(
            membership,
            actor_user_id,
            expected_version,
        )

    async def _ensure_owner(self, store: Store) -> StoreMembership:
        owner = await self._memberships.get_owner(store.id)
        if owner is None:
            return await self._memberships.add_owner(
                store_id=store.id,
                user_id=store.owner_id,
                accepted_at=store.created_at,
            )
        if owner.user_id != store.owner_id:
            raise _conflict("The persisted Store owner membership is inconsistent.")
        return owner

    async def _owned_store(self, store_id: UUID, owner_id: UUID) -> Store:
        store = await self._stores.get_for_owner(store_id, owner_id)
        if store is None:
            raise _store_not_found()
        return store

    async def _require_store(self, store_id: UUID) -> Store:
        store = await self._stores.get_by_id(store_id)
        if store is None:
            raise _store_not_found()
        return store

    async def _require_membership(
        self,
        store_id: UUID,
        membership_id: UUID,
    ) -> StoreMembership:
        membership = await self._memberships.get(store_id, membership_id)
        if membership is None:
            raise _membership_not_found()
        return membership


def _store_not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Store not found",
        detail="The requested Store was not found.",
        status_code=404,
    )


def _membership_not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Store membership not found",
        detail="The requested Store membership was not found.",
        status_code=404,
    )


def _user_not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="User not found",
        detail="The invited user was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Store membership conflict",
        detail=detail,
        status_code=409,
    )


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Store membership validation failed",
        detail="One or more Store membership fields are invalid.",
        status_code=422,
        errors=[
            FieldError(
                field=field,
                code="invalid_store_membership_field",
                message=message,
            )
        ],
    )


def _correlation_id() -> UUID | None:
    context = maybe_get_request_context()
    return context.correlation_id if context is not None else None
