from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from uuid6 import uuid7

from app.common.context import maybe_get_request_context
from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.stores.application.media_repositories import (
    StoreMediaConstraintError,
    StoreMediaRepository,
)
from app.modules.stores.application.media_schemas import (
    StoreMediaReorderItem,
    StoreMediaUpdate,
    StoreMediaUpload,
)
from app.modules.stores.application.media_storage import (
    StorageError,
    StorageProvider,
)
from app.modules.stores.application.media_validation import (
    StoreMediaValidationService,
)
from app.modules.stores.application.repositories import StoreRepository
from app.modules.stores.domain import (
    StoreBannerUploaded,
    StoreGalleryUploaded,
    StoreLogoUploaded,
    StoreMedia,
    StoreMediaDeleted,
    StoreMediaEvent,
    StoreMediaReordered,
    StoreMediaType,
)
from app.modules.stores.infrastructure.media_transactions import (
    StoreMediaStorageTransaction,
)
from app.observability.metrics import (
    STORE_MEDIA_BYTES,
    STORE_MEDIA_DELETES,
    STORE_MEDIA_FAILURES,
    STORE_MEDIA_UPLOADS,
)


class StoreMediaAuditService:
    def __init__(self, events: EventPublisher) -> None:
        self._events = events

    async def publish(
        self,
        event_type: type[StoreMediaEvent],
        media: StoreMedia,
    ) -> None:
        await self._events.publish(
            event_type(
                store_id=media.store_id,
                media_id=media.id,
                media_type=media.media_type,
                correlation_id=_correlation_id(),
            )
        )


class StoreMediaService:
    """Owner-scoped Store image lifecycle and storage orchestration."""

    def __init__(
        self,
        stores: StoreRepository,
        media: StoreMediaRepository,
        storage: StorageProvider,
        storage_transaction: StoreMediaStorageTransaction,
        validation: StoreMediaValidationService,
        audit: StoreMediaAuditService,
        *,
        bucket: str,
        presigned_expiration_seconds: int,
    ) -> None:
        self._stores = stores
        self._media = media
        self._storage = storage
        self._storage_transaction = storage_transaction
        self._validation = validation
        self._audit = audit
        self._bucket = bucket
        self._presigned_expiration = timedelta(seconds=presigned_expiration_seconds)

    async def upload(
        self,
        store_id: UUID,
        actor_user_id: UUID,
        media_type: StoreMediaType,
        upload: StoreMediaUpload,
    ) -> StoreMedia:
        await self._owned_store(store_id, actor_user_id)
        try:
            validated = self._validation.validate(media_type, upload)
            duplicate = await self._media.find_duplicate(
                store_id,
                validated.checksum_sha256,
            )
            if duplicate is not None:
                raise _conflict("The same image already exists for this Store.")

            object_id = uuid7()
            directory = {
                StoreMediaType.LOGO: "logos",
                StoreMediaType.BANNER: "banners",
                StoreMediaType.GALLERY: "gallery",
            }[media_type]
            stored_filename = f"{object_id}{validated.extension}"
            object_key = f"stores/{store_id}/{directory}/{stored_filename}"
            stored = await self._storage_transaction.upload(
                self._bucket,
                object_key,
                validated.data,
                content_type=validated.mime_type,
            )
            if media_type in {StoreMediaType.LOGO, StoreMediaType.BANNER}:
                await self._media.archive_active(store_id, media_type)
            media = await self._media.add(
                store_id=store_id,
                uploaded_by_id=actor_user_id,
                media_type=media_type,
                original_filename=validated.original_filename,
                stored_filename=stored_filename,
                extension=validated.extension,
                mime_type=validated.mime_type,
                file_size=validated.file_size,
                width=validated.width,
                height=validated.height,
                orientation=validated.orientation,
                aspect_ratio=validated.aspect_ratio,
                checksum_sha256=validated.checksum_sha256,
                bucket=stored.bucket,
                object_key=stored.object_key,
                etag=stored.etag,
                display_order=validated.display_order,
                is_public=validated.is_public,
            )
            event_type = {
                StoreMediaType.LOGO: StoreLogoUploaded,
                StoreMediaType.BANNER: StoreBannerUploaded,
                StoreMediaType.GALLERY: StoreGalleryUploaded,
            }[media_type]
            await self._audit.publish(event_type, media)
            STORE_MEDIA_UPLOADS.inc()
            STORE_MEDIA_BYTES.inc(validated.file_size)
            return media
        except StorageError as error:
            STORE_MEDIA_FAILURES.inc()
            raise _storage_unavailable() from error
        except StoreMediaConstraintError as error:
            STORE_MEDIA_FAILURES.inc()
            raise _conflict(
                "A matching or singleton Store image already exists."
            ) from error
        except AppError:
            STORE_MEDIA_FAILURES.inc()
            raise

    async def list(
        self,
        store_id: UUID,
        actor_user_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[StoreMedia], int]:
        await self._owned_store(store_id, actor_user_id)
        return await self._media.list_for_store(
            store_id,
            offset=offset,
            limit=limit,
        )

    async def get(
        self,
        store_id: UUID,
        media_id: UUID,
        actor_user_id: UUID,
    ) -> StoreMedia:
        await self._owned_store(store_id, actor_user_id)
        return await self._require_media(store_id, media_id)

    async def update(
        self,
        store_id: UUID,
        media_id: UUID,
        actor_user_id: UUID,
        changes: StoreMediaUpdate,
    ) -> StoreMedia:
        await self._owned_store(store_id, actor_user_id)
        await self._require_media(store_id, media_id)
        values: dict[str, object] = {}
        if changes.display_order is not None:
            if changes.display_order < 0:
                raise _validation(
                    "display_order",
                    "Display order must be zero or greater.",
                )
            values["display_order"] = changes.display_order
        if changes.is_public is not None:
            values["is_public"] = changes.is_public
        if not values:
            raise _validation("body", "At least one metadata change is required.")
        updated = await self._media.update(
            store_id,
            media_id,
            values=values,
            expected_version=changes.expected_version,
        )
        if updated is None:
            raise _conflict("The Store media changed during the update.")
        return updated

    async def delete(
        self,
        store_id: UUID,
        media_id: UUID,
        actor_user_id: UUID,
    ) -> None:
        await self._owned_store(store_id, actor_user_id)
        media = await self._require_media(store_id, media_id)
        try:
            await self._storage_transaction.stage_delete(
                media.bucket,
                media.object_key,
            )
            deleted = await self._media.soft_delete(
                store_id,
                media_id,
                deleted_at=datetime.now(UTC),
                expected_version=media.version,
            )
            if deleted is None:
                raise _conflict("The Store media changed during deletion.")
            await self._audit.publish(StoreMediaDeleted, deleted)
            STORE_MEDIA_DELETES.inc()
        except StorageError as error:
            STORE_MEDIA_FAILURES.inc()
            raise _storage_unavailable() from error

    async def reorder(
        self,
        store_id: UUID,
        actor_user_id: UUID,
        items: Sequence[StoreMediaReorderItem],
    ) -> Sequence[StoreMedia]:
        await self._owned_store(store_id, actor_user_id)
        if not items:
            raise _validation("items", "At least one gallery item is required.")
        if len({item.media_id for item in items}) != len(items):
            raise _validation("items", "Gallery media identifiers must be unique.")
        if len({item.display_order for item in items}) != len(items):
            raise _validation("items", "Gallery display orders must be unique.")
        reordered: list[StoreMedia] = []
        for item in items:
            media = await self._require_media(store_id, item.media_id)
            if media.media_type is not StoreMediaType.GALLERY:
                raise _validation(
                    "items",
                    "Only gallery images can be reordered.",
                )
            if item.display_order < 0:
                raise _validation(
                    "display_order",
                    "Display order must be zero or greater.",
                )
            updated = await self._media.update(
                store_id,
                item.media_id,
                values={"display_order": item.display_order},
                expected_version=item.expected_version,
            )
            if updated is None:
                raise _conflict("A gallery image changed during reordering.")
            await self._audit.publish(StoreMediaReordered, updated)
            reordered.append(updated)
        return reordered

    async def generate_download_url(self, media: StoreMedia) -> tuple[str, datetime]:
        try:
            url = await self._storage.generate_presigned_download(
                media.bucket,
                media.object_key,
                expires=self._presigned_expiration,
            )
        except StorageError as error:
            STORE_MEDIA_FAILURES.inc()
            raise _storage_unavailable() from error
        return url, datetime.now(UTC) + self._presigned_expiration

    async def _owned_store(self, store_id: UUID, owner_id: UUID) -> None:
        if await self._stores.get_for_owner(store_id, owner_id) is None:
            raise _store_not_found()

    async def _require_media(
        self,
        store_id: UUID,
        media_id: UUID,
    ) -> StoreMedia:
        media = await self._media.get(store_id, media_id)
        if media is None:
            raise _media_not_found()
        return media


def _store_not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Store not found",
        detail="The requested Store was not found.",
        status_code=404,
    )


def _media_not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Store media not found",
        detail="The requested Store media was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Store media conflict",
        detail=detail,
        status_code=409,
    )


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Store media validation failed",
        detail="One or more Store media fields are invalid.",
        status_code=422,
        errors=[
            FieldError(
                field=field,
                code="invalid_store_media",
                message=message,
            )
        ],
    )


def _storage_unavailable() -> AppError:
    return AppError(
        code=ErrorCode.INTERNAL_SERVER_ERROR,
        title="Store media storage unavailable",
        detail="The Store media operation could not be completed.",
        status_code=503,
    )


def _correlation_id() -> UUID | None:
    context = maybe_get_request_context()
    return context.correlation_id if context is not None else None
