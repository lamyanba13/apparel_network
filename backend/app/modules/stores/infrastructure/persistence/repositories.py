from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stores.application.repositories import StoreRepository
from app.modules.stores.domain import (
    Store,
    StoreAddress,
    StoreContact,
    StoreStatus,
    VerificationStatus,
)
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyStoreRepository(StoreRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        owner_id: UUID,
        name: str,
        slug: str,
        description: str | None,
        contact: StoreContact,
        address: StoreAddress,
        logo_url: str | None,
        banner_url: str | None,
    ) -> Store:
        model = StoreModel(
            owner_id=owner_id,
            name=name,
            slug=slug,
            description=description,
            phone=contact.phone,
            email=contact.email,
            website=contact.website,
            address=address.address,
            city=address.city,
            district=address.district,
            state=address.state,
            country=address.country,
            postal_code=address.postal_code,
            latitude=address.latitude,
            longitude=address.longitude,
            logo_url=logo_url,
            banner_url=banner_url,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _store(model)

    async def slug_exists(self, slug: str) -> bool:
        value = await self._session.scalar(
            select(StoreModel.id).where(StoreModel.slug == slug).limit(1)
        )
        return value is not None

    async def list_for_owner(
        self,
        owner_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Store], int]:
        where = (
            StoreModel.owner_id == owner_id,
            StoreModel.deleted_at.is_(None),
        )
        result = await self._session.scalars(
            select(StoreModel)
            .where(*where)
            .order_by(StoreModel.created_at.desc(), StoreModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        total = await self._session.scalar(
            select(func.count()).select_from(StoreModel).where(*where)
        )
        return [_store(model) for model in result], int(total or 0)

    async def get_for_owner(self, store_id: UUID, owner_id: UUID) -> Store | None:
        model = await self._session.scalar(
            select(StoreModel).where(
                StoreModel.id == store_id,
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
            )
        )
        return _store(model) if model is not None else None

    async def get_by_id(self, store_id: UUID) -> Store | None:
        model = await self._session.scalar(
            select(StoreModel).where(
                StoreModel.id == store_id,
                StoreModel.deleted_at.is_(None),
            )
        )
        return _store(model) if model is not None else None

    async def update(
        self,
        store_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> Store | None:
        result = await self._session.execute(
            update(StoreModel)
            .where(
                StoreModel.id == store_id,
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
                StoreModel.version == expected_version,
                StoreModel.status != StoreStatus.CLOSED,
            )
            .values(
                **dict(values),
                updated_at=func.now(),
                version=StoreModel.version + 1,
            )
            .returning(StoreModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _store(model) if model is not None else None

    async def transition(
        self,
        store_id: UUID,
        *,
        from_statuses: frozenset[StoreStatus],
        status: StoreStatus,
        verification_status: VerificationStatus | None = None,
        deleted_at: datetime | None = None,
    ) -> Store | None:
        values: dict[str, object] = {
            "status": status,
            "updated_at": func.now(),
            "version": StoreModel.version + 1,
        }
        if verification_status is not None:
            values["verification_status"] = verification_status
        if deleted_at is not None:
            values["deleted_at"] = deleted_at
        result = await self._session.execute(
            update(StoreModel)
            .where(
                StoreModel.id == store_id,
                StoreModel.deleted_at.is_(None),
                StoreModel.status.in_(from_statuses),
            )
            .values(**values)
            .returning(StoreModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _store(model) if model is not None else None

    async def close_for_owner(
        self,
        store_id: UUID,
        owner_id: UUID,
        *,
        deleted_at: datetime,
    ) -> Store | None:
        result = await self._session.execute(
            update(StoreModel)
            .where(
                StoreModel.id == store_id,
                StoreModel.owner_id == owner_id,
                StoreModel.deleted_at.is_(None),
                StoreModel.status != StoreStatus.CLOSED,
            )
            .values(
                status=StoreStatus.CLOSED,
                deleted_at=deleted_at,
                updated_at=func.now(),
                version=StoreModel.version + 1,
            )
            .returning(StoreModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _store(model) if model is not None else None

    async def count_active_and_verified(self) -> tuple[int, int]:
        active = await self._session.scalar(
            select(func.count())
            .select_from(StoreModel)
            .where(
                StoreModel.deleted_at.is_(None),
                StoreModel.status == StoreStatus.ACTIVE,
            )
        )
        verified = await self._session.scalar(
            select(func.count())
            .select_from(StoreModel)
            .where(
                StoreModel.deleted_at.is_(None),
                StoreModel.verification_status == VerificationStatus.VERIFIED,
            )
        )
        return int(active or 0), int(verified or 0)


def _store(model: StoreModel) -> Store:
    return Store(
        id=model.id,
        owner_id=model.owner_id,
        name=model.name,
        slug=model.slug,
        description=model.description,
        contact=StoreContact(
            phone=model.phone,
            email=model.email,
            website=model.website,
        ),
        address=StoreAddress(
            address=model.address,
            city=model.city,
            district=model.district,
            state=model.state,
            country=model.country,
            postal_code=model.postal_code,
            latitude=model.latitude,
            longitude=model.longitude,
        ),
        logo_url=model.logo_url,
        banner_url=model.banner_url,
        status=model.status,
        verification_status=model.verification_status,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        version=model.version,
    )
