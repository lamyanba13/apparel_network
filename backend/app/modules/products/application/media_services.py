from collections.abc import Sequence
from datetime import timedelta
from pathlib import PurePath
from uuid import UUID

from uuid6 import uuid7

from app.common.errors import ErrorCode
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.products.domain.media import (
    ProductMedia,
    ProductMediaRole,
    ProductMediaType,
)
from app.modules.products.infrastructure.media_repositories import (
    ProductMediaRepository,
)
from app.modules.stores.application.media_storage import StorageProvider
from app.modules.stores.infrastructure.media_transactions import (
    StoreMediaStorageTransaction,
)
from app.observability.metrics import (
    PRODUCT_MEDIA_BYTES,
    PRODUCT_MEDIA_DELETES,
    PRODUCT_MEDIA_UPLOADS,
)


class ProductMediaService:
    def __init__(
        self,
        repository: ProductMediaRepository,
        storage: StorageProvider,
        transaction: StoreMediaStorageTransaction,
        events: EventPublisher,
        bucket: str,
        expiration: int,
    ) -> None:
        self.repository, self.storage, self.transaction, self.events = (
            repository,
            storage,
            transaction,
            events,
        )
        self.bucket, self.expiration = bucket, timedelta(seconds=expiration)

    async def upload(
        self,
        product_id: UUID,
        owner_id: UUID,
        role: ProductMediaRole,
        filename: str,
        content_type: str,
        data: bytes,
        variant_id: UUID | None = None,
    ) -> ProductMedia:
        product = await self.repository.get_product(product_id, owner_id)
        if product is None:
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                title="Product not found",
                detail="Product not found.",
                status_code=404,
            )
        if variant_id is not None and not await self.repository.variant_in_product(
            product_id, variant_id, owner_id
        ):
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                title="Product Variant not found",
                detail="Product Variant not found.",
                status_code=404,
            )
        allowed = {
            "image/jpeg": (ProductMediaType.IMAGE, ".jpg"),
            "image/png": (ProductMediaType.IMAGE, ".png"),
            "image/webp": (ProductMediaType.IMAGE, ".webp"),
            "image/avif": (ProductMediaType.IMAGE, ".avif"),
            "video/mp4": (ProductMediaType.VIDEO, ".mp4"),
        }
        if content_type not in allowed or not data:
            raise AppError(
                code=ErrorCode.VALIDATION_ERROR,
                title="Invalid media",
                detail="Unsupported media.",
                status_code=422,
            )
        media_type, extension = allowed[content_type]
        if (
            role is ProductMediaRole.PRIMARY
            and media_type is not ProductMediaType.IMAGE
        ):
            raise AppError(
                code=ErrorCode.VALIDATION_ERROR,
                title="Invalid media",
                detail="Primary media must be an image.",
                status_code=422,
            )
        if role is ProductMediaRole.PRIMARY:
            await self.repository.archive_primary(product_id)
        object_key = f"products/{product_id}/{role.value}/{uuid7()}{extension}"
        stored = await self.transaction.upload(
            self.bucket, object_key, data, content_type=content_type
        )
        media = await self.repository.add(
            dict(
                product_id=product.id,
                variant_id=variant_id,
                store_id=product.store_id,
                catalog_id=product.catalog_id,
                media_type=media_type,
                role=role,
                storage_provider="minio",
                bucket=stored.bucket,
                object_key=stored.object_key,
                original_filename=PurePath(filename).name[:255] or "upload",
                mime_type=content_type,
                extension=extension,
                file_size=len(data),
                width=None,
                height=None,
                duration_seconds=None,
                checksum_sha256=__import__("hashlib").sha256(data).hexdigest(),
                display_order=0,
                is_active=True,
                created_by_id=owner_id,
            )
        )
        PRODUCT_MEDIA_UPLOADS.inc()
        PRODUCT_MEDIA_BYTES.inc(len(data))
        return media

    async def list(self, product_id: UUID, owner_id: UUID) -> Sequence[ProductMedia]:
        if await self.repository.get_product(product_id, owner_id) is None:
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                title="Product not found",
                detail="Product not found.",
                status_code=404,
            )
        return await self.repository.list(product_id)

    async def delete(
        self, product_id: UUID, media_id: UUID, owner_id: UUID, version: int
    ) -> None:
        media = await self.repository.get(product_id, media_id)
        if (
            media is None
            or await self.repository.get_product(product_id, owner_id) is None
        ):
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                title="Media not found",
                detail="Media not found.",
                status_code=404,
            )
        await self.transaction.stage_delete(media.bucket, media.object_key)
        if await self.repository.soft_delete(product_id, media_id, version) is None:
            raise AppError(
                code=ErrorCode.CONFLICT,
                title="Media conflict",
                detail="Media changed.",
                status_code=409,
            )
        PRODUCT_MEDIA_DELETES.inc()
