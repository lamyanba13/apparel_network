from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stores.application.media_repositories import (
    StoreMediaConstraintError,
    StoreMediaRepository,
)
from app.modules.stores.domain import StoreMedia, StoreMediaStatus, StoreMediaType
from app.modules.stores.infrastructure.persistence.media_models import StoreMediaModel


class SqlAlchemyStoreMediaRepository(StoreMediaRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        store_id: UUID,
        uploaded_by_id: UUID,
        media_type: StoreMediaType,
        original_filename: str,
        stored_filename: str,
        extension: str,
        mime_type: str,
        file_size: int,
        width: int,
        height: int,
        orientation: int,
        aspect_ratio: Decimal,
        checksum_sha256: str,
        bucket: str,
        object_key: str,
        etag: str,
        display_order: int,
        is_public: bool,
    ) -> StoreMedia:
        model = StoreMediaModel(
            store_id=store_id,
            uploaded_by_id=uploaded_by_id,
            media_type=media_type,
            status=StoreMediaStatus.ACTIVE,
            original_filename=original_filename,
            stored_filename=stored_filename,
            extension=extension,
            mime_type=mime_type,
            file_size=file_size,
            width=width,
            height=height,
            orientation=orientation,
            aspect_ratio=Decimal(str(aspect_ratio)),
            checksum_sha256=checksum_sha256,
            bucket=bucket,
            object_key=object_key,
            etag=etag,
            display_order=display_order,
            is_public=is_public,
        )
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise StoreMediaConstraintError from error
        await self._session.refresh(model)
        return _media(model)

    async def get(
        self,
        store_id: UUID,
        media_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> StoreMedia | None:
        statement = select(StoreMediaModel).where(
            StoreMediaModel.id == media_id,
            StoreMediaModel.store_id == store_id,
        )
        if not include_deleted:
            statement = statement.where(StoreMediaModel.deleted_at.is_(None))
        model = await self._session.scalar(statement)
        return _media(model) if model is not None else None

    async def list_for_store(
        self,
        store_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[StoreMedia], int]:
        where = (
            StoreMediaModel.store_id == store_id,
            StoreMediaModel.deleted_at.is_(None),
        )
        result = await self._session.scalars(
            select(StoreMediaModel)
            .where(*where)
            .order_by(
                StoreMediaModel.media_type,
                StoreMediaModel.display_order,
                StoreMediaModel.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        total = await self._session.scalar(
            select(func.count()).select_from(StoreMediaModel).where(*where)
        )
        return [_media(model) for model in result], int(total or 0)

    async def find_duplicate(
        self,
        store_id: UUID,
        checksum_sha256: str,
    ) -> StoreMedia | None:
        model = await self._session.scalar(
            select(StoreMediaModel).where(
                StoreMediaModel.store_id == store_id,
                StoreMediaModel.checksum_sha256 == checksum_sha256,
                StoreMediaModel.deleted_at.is_(None),
            )
        )
        return _media(model) if model is not None else None

    async def archive_active(
        self,
        store_id: UUID,
        media_type: StoreMediaType,
    ) -> int:
        result = await self._session.execute(
            update(StoreMediaModel)
            .where(
                StoreMediaModel.store_id == store_id,
                StoreMediaModel.media_type == media_type,
                StoreMediaModel.status == StoreMediaStatus.ACTIVE,
                StoreMediaModel.deleted_at.is_(None),
            )
            .values(
                status=StoreMediaStatus.ARCHIVED,
                updated_at=func.now(),
                version=StoreMediaModel.version + 1,
            )
            .returning(StoreMediaModel.id)
        )
        await self._session.flush()
        return len(result.scalars().all())

    async def update(
        self,
        store_id: UUID,
        media_id: UUID,
        *,
        values: Mapping[str, object],
        expected_version: int,
    ) -> StoreMedia | None:
        result = await self._session.execute(
            update(StoreMediaModel)
            .where(
                StoreMediaModel.id == media_id,
                StoreMediaModel.store_id == store_id,
                StoreMediaModel.deleted_at.is_(None),
                StoreMediaModel.version == expected_version,
            )
            .values(
                **dict(values),
                updated_at=func.now(),
                version=StoreMediaModel.version + 1,
            )
            .returning(StoreMediaModel)
        )
        await self._session.flush()
        model = result.scalar_one_or_none()
        return _media(model) if model is not None else None

    async def soft_delete(
        self,
        store_id: UUID,
        media_id: UUID,
        *,
        deleted_at: datetime,
        expected_version: int,
    ) -> StoreMedia | None:
        return await self.update(
            store_id,
            media_id,
            values={
                "status": StoreMediaStatus.DELETED,
                "deleted_at": deleted_at,
            },
            expected_version=expected_version,
        )

    async def count_active(self) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(StoreMediaModel)
            .where(
                StoreMediaModel.status == StoreMediaStatus.ACTIVE,
                StoreMediaModel.deleted_at.is_(None),
            )
        )
        return int(total or 0)


def _media(model: StoreMediaModel) -> StoreMedia:
    return StoreMedia(
        id=model.id,
        store_id=model.store_id,
        uploaded_by_id=model.uploaded_by_id,
        media_type=model.media_type,
        status=model.status,
        original_filename=model.original_filename,
        stored_filename=model.stored_filename,
        extension=model.extension,
        mime_type=model.mime_type,
        file_size=model.file_size,
        width=model.width,
        height=model.height,
        orientation=model.orientation,
        aspect_ratio=model.aspect_ratio,
        checksum_sha256=model.checksum_sha256,
        bucket=model.bucket,
        object_key=model.object_key,
        etag=model.etag,
        display_order=model.display_order,
        is_public=model.is_public,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        version=model.version,
    )
