from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalogs.domain import Catalog, CatalogStatus
from app.modules.catalogs.infrastructure.models import CatalogModel
from app.modules.stores.infrastructure.persistence.models import StoreModel


class SqlAlchemyCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store_owned(self, store_id: UUID, owner_id: UUID) -> bool:
        return (
            await self._session.scalar(
                select(StoreModel.id).where(
                    StoreModel.id == store_id,
                    StoreModel.owner_id == owner_id,
                    StoreModel.deleted_at.is_(None),
                )
            )
            is not None
        )

    async def add(self, values: Mapping[str, object]) -> Catalog:
        persisted = dict(values)
        actor_id = persisted.pop("actor_id", None)
        model = CatalogModel(
            **persisted,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def list_for_owner(
        self, owner_id: UUID, *, offset: int, limit: int
    ) -> tuple[Sequence[Catalog], int]:
        base = (
            select(CatalogModel)
            .join(StoreModel, StoreModel.id == CatalogModel.store_id)
            .where(StoreModel.owner_id == owner_id, CatalogModel.deleted_at.is_(None))
        )
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(base.subquery())
            )
            or 0
        )
        rows = (
            await self._session.scalars(
                base.order_by(CatalogModel.sort_order, CatalogModel.name)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [_to_domain(row) for row in rows], total

    async def get_for_owner(self, catalog_id: UUID, owner_id: UUID) -> Catalog | None:
        query = (
            select(CatalogModel)
            .join(StoreModel, StoreModel.id == CatalogModel.store_id)
            .where(
                CatalogModel.id == catalog_id,
                StoreModel.owner_id == owner_id,
                CatalogModel.deleted_at.is_(None),
            )
        )
        model = await self._session.scalar(query)
        return _to_domain(model) if model else None

    async def slug_exists(
        self, store_id: UUID, slug: str, *, exclude_id: UUID | None = None
    ) -> bool:
        query = select(CatalogModel.id).where(
            CatalogModel.store_id == store_id,
            CatalogModel.slug == slug,
            CatalogModel.deleted_at.is_(None),
        )
        if exclude_id is not None:
            query = query.where(CatalogModel.id != exclude_id)
        return await self._session.scalar(query) is not None

    async def update(
        self,
        catalog_id: UUID,
        owner_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> Catalog | None:
        model = await self._session.scalar(
            select(CatalogModel)
            .join(StoreModel)
            .where(
                CatalogModel.id == catalog_id,
                StoreModel.owner_id == owner_id,
                CatalogModel.deleted_at.is_(None),
                CatalogModel.version == expected_version,
            )
        )
        if model is None:
            return None
        for key, value in values.items():
            setattr(model, key, value)
        if values.get("is_default") is True:
            model.status = CatalogStatus.ACTIVE
            model.activated_at = model.activated_at or datetime.now(UTC)
        model.updated_by_id = owner_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def archive(
        self,
        catalog_id: UUID,
        owner_id: UUID,
        *,
        expected_version: int,
        deleted_at: datetime | None = None,
    ) -> Catalog | None:
        return await self._transition(
            catalog_id, owner_id, CatalogStatus.ARCHIVED, expected_version, deleted_at
        )

    async def transition(
        self,
        catalog_id: UUID,
        owner_id: UUID,
        *,
        status: CatalogStatus,
        expected_version: int,
    ) -> Catalog | None:
        return await self._transition(
            catalog_id, owner_id, status, expected_version, None
        )

    async def _transition(
        self,
        catalog_id: UUID,
        owner_id: UUID,
        status: CatalogStatus,
        expected_version: int,
        deleted_at: datetime | None,
    ) -> Catalog | None:
        model = await self._session.scalar(
            select(CatalogModel)
            .join(StoreModel)
            .where(
                CatalogModel.id == catalog_id,
                StoreModel.owner_id == owner_id,
                CatalogModel.deleted_at.is_(None),
                CatalogModel.version == expected_version,
            )
        )
        if model is None:
            return None
        model.status = status
        if status is CatalogStatus.ACTIVE:
            model.activated_at = model.activated_at or datetime.now(UTC)
        if status is CatalogStatus.ARCHIVED:
            model.archived_at = model.archived_at or datetime.now(UTC)
        if deleted_at is not None:
            model.deleted_at = deleted_at
        model.updated_by_id = owner_id
        model.version += 1
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)


def _to_domain(model: CatalogModel) -> Catalog:
    return Catalog(
        id=model.id,
        store_id=model.store_id,
        name=model.name,
        slug=model.slug,
        description=model.description,
        status=model.status,
        visibility=model.visibility,
        sort_order=model.sort_order,
        activated_at=model.activated_at,
        archived_at=model.archived_at,
        is_default=model.is_default,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        version=model.version,
        created_by_id=model.created_by_id,
        updated_by_id=model.updated_by_id,
    )
