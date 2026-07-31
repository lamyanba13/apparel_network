from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stores.application.membership_repositories import (
    StoreMembershipRepository,
)
from app.modules.stores.domain import (
    StoreMembership,
    StoreMembershipRole,
    StoreMembershipStatus,
)
from app.modules.stores.infrastructure.persistence.membership_models import (
    StoreMembershipModel,
)


class SqlAlchemyStoreMembershipRepository(StoreMembershipRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_owner(
        self,
        *,
        store_id: UUID,
        user_id: UUID,
        accepted_at: datetime,
    ) -> StoreMembership:
        model = StoreMembershipModel(
            store_id=store_id,
            user_id=user_id,
            role=StoreMembershipRole.OWNER,
            status=StoreMembershipStatus.ACTIVE,
            invited_by_id=user_id,
            accepted_at=accepted_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _membership(model)

    async def add_invitation(
        self,
        *,
        store_id: UUID,
        user_id: UUID,
        role: StoreMembershipRole,
        invited_by_id: UUID,
        expires_at: datetime,
    ) -> StoreMembership:
        model = StoreMembershipModel(
            store_id=store_id,
            user_id=user_id,
            role=role,
            status=StoreMembershipStatus.PENDING,
            invited_by_id=invited_by_id,
            invitation_expires_at=expires_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _membership(model)

    async def get(
        self,
        store_id: UUID,
        membership_id: UUID,
    ) -> StoreMembership | None:
        model = await self._session.scalar(
            select(StoreMembershipModel).where(
                StoreMembershipModel.id == membership_id,
                StoreMembershipModel.store_id == store_id,
            )
        )
        return _membership(model) if model is not None else None

    async def get_owner(self, store_id: UUID) -> StoreMembership | None:
        model = await self._session.scalar(
            select(StoreMembershipModel).where(
                StoreMembershipModel.store_id == store_id,
                StoreMembershipModel.role == StoreMembershipRole.OWNER,
                StoreMembershipModel.status == StoreMembershipStatus.ACTIVE,
            )
        )
        return _membership(model) if model is not None else None

    async def find_open(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> StoreMembership | None:
        model = await self._session.scalar(
            select(StoreMembershipModel)
            .where(
                StoreMembershipModel.store_id == store_id,
                StoreMembershipModel.user_id == user_id,
                StoreMembershipModel.status.in_(
                    {
                        StoreMembershipStatus.PENDING,
                        StoreMembershipStatus.ACTIVE,
                        StoreMembershipStatus.SUSPENDED,
                    }
                ),
            )
            .order_by(StoreMembershipModel.created_at.desc())
            .limit(1)
        )
        return _membership(model) if model is not None else None

    async def list_for_store(
        self,
        store_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[StoreMembership], int]:
        result = await self._session.scalars(
            select(StoreMembershipModel)
            .where(StoreMembershipModel.store_id == store_id)
            .order_by(
                StoreMembershipModel.created_at.desc(),
                StoreMembershipModel.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        total = await self._session.scalar(
            select(func.count())
            .select_from(StoreMembershipModel)
            .where(StoreMembershipModel.store_id == store_id)
        )
        return [_membership(model) for model in result], int(total or 0)

    async def transition(
        self,
        membership_id: UUID,
        *,
        from_statuses: frozenset[StoreMembershipStatus],
        status: StoreMembershipStatus,
        expected_version: int,
        accepted_at: datetime | None = None,
        removed_at: datetime | None = None,
    ) -> StoreMembership | None:
        values: dict[str, object] = {
            "status": status,
            "updated_at": func.now(),
            "version": StoreMembershipModel.version + 1,
        }
        if accepted_at is not None:
            values["accepted_at"] = accepted_at
            values["invitation_expires_at"] = None
        if removed_at is not None:
            values["removed_at"] = removed_at
        result = await self._session.execute(
            update(StoreMembershipModel)
            .where(
                StoreMembershipModel.id == membership_id,
                StoreMembershipModel.status.in_(from_statuses),
                StoreMembershipModel.version == expected_version,
            )
            .values(**values)
            .returning(StoreMembershipModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _membership(model) if model is not None else None

    async def update_role(
        self,
        membership_id: UUID,
        *,
        role: StoreMembershipRole,
        expected_version: int,
    ) -> StoreMembership | None:
        result = await self._session.execute(
            update(StoreMembershipModel)
            .where(
                StoreMembershipModel.id == membership_id,
                StoreMembershipModel.role != StoreMembershipRole.OWNER,
                StoreMembershipModel.status.in_(
                    {
                        StoreMembershipStatus.PENDING,
                        StoreMembershipStatus.ACTIVE,
                        StoreMembershipStatus.SUSPENDED,
                    }
                ),
                StoreMembershipModel.version == expected_version,
            )
            .values(
                role=role,
                updated_at=func.now(),
                version=StoreMembershipModel.version + 1,
            )
            .returning(StoreMembershipModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _membership(model) if model is not None else None

    async def expire_pending(self, store_id: UUID, *, now: datetime) -> int:
        result = await self._session.execute(
            update(StoreMembershipModel)
            .where(
                StoreMembershipModel.store_id == store_id,
                StoreMembershipModel.status == StoreMembershipStatus.PENDING,
                StoreMembershipModel.invitation_expires_at <= now,
            )
            .values(
                status=StoreMembershipStatus.EXPIRED,
                removed_at=now,
                updated_at=func.now(),
                version=StoreMembershipModel.version + 1,
            )
            .returning(StoreMembershipModel.id)
        )
        await self._session.flush()
        return len(result.scalars().all())

    async def count_current(self) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(StoreMembershipModel)
            .where(
                StoreMembershipModel.status.in_(
                    {
                        StoreMembershipStatus.ACTIVE,
                        StoreMembershipStatus.SUSPENDED,
                    }
                )
            )
        )
        return int(total or 0)


def _membership(model: StoreMembershipModel) -> StoreMembership:
    return StoreMembership(
        id=model.id,
        store_id=model.store_id,
        user_id=model.user_id,
        role=model.role,
        status=model.status,
        invited_by_id=model.invited_by_id,
        invitation_expires_at=model.invitation_expires_at,
        accepted_at=model.accepted_at,
        removed_at=model.removed_at,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
