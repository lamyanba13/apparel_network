from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from PIL import Image
from prometheus_client import generate_latest
from pytest import MonkeyPatch
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.common.api import install_custom_openapi
from app.common.events import DomainEvent
from app.common.exceptions import AppError
from app.core.config import Settings, get_settings
from app.modules.identity.application.schemas import UserCreate
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyUserRepository,
)
from app.modules.stores.api.media_router import router as media_router
from app.modules.stores.application.media_schemas import (
    StoreMediaReorderItem,
    StoreMediaUpdate,
    StoreMediaUpload,
)
from app.modules.stores.application.media_services import (
    StoreMediaAuditService,
    StoreMediaService,
)
from app.modules.stores.application.media_storage import (
    StorageError,
    StorageObject,
)
from app.modules.stores.application.media_validation import (
    StoreMediaValidationService,
)
from app.modules.stores.application.schemas import StoreCreate
from app.modules.stores.application.services import (
    StoreService,
    StoreSlugService,
    StoreValidationService,
)
from app.modules.stores.domain import (
    StoreAddress,
    StoreContact,
    StoreMediaStatus,
    StoreMediaType,
)
from app.modules.stores.infrastructure.media_storage import MinIOStorageProvider
from app.modules.stores.infrastructure.media_transactions import (
    StoreMediaStorageTransaction,
)
from app.modules.stores.infrastructure.persistence.media_repositories import (
    SqlAlchemyStoreMediaRepository,
)
from app.modules.stores.infrastructure.persistence.repositories import (
    SqlAlchemyStoreRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$ZGlnaWVzdA"
BUCKET = "fashion-network-media"


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    async def upload(
        self,
        bucket: str,
        object_key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> StorageObject:
        self.objects[(bucket, object_key)] = (data, content_type)
        return StorageObject(bucket, object_key, "memory-etag", len(data), content_type)

    async def download(self, bucket: str, object_key: str) -> bytes:
        try:
            return self.objects[(bucket, object_key)][0]
        except KeyError as error:
            raise StorageError("Object not found.") from error

    async def delete(self, bucket: str, object_key: str) -> None:
        self.objects.pop((bucket, object_key), None)

    async def copy(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> StorageObject:
        data, content_type = self.objects[(source_bucket, source_key)]
        return await self.upload(
            destination_bucket,
            destination_key,
            data,
            content_type=content_type,
        )

    async def move(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> StorageObject:
        copied = await self.copy(
            source_bucket,
            source_key,
            destination_bucket,
            destination_key,
        )
        await self.delete(source_bucket, source_key)
        return copied

    async def exists(self, bucket: str, object_key: str) -> bool:
        return (bucket, object_key) in self.objects

    async def stat(self, bucket: str, object_key: str) -> StorageObject:
        data, content_type = self.objects[(bucket, object_key)]
        return StorageObject(
            bucket,
            object_key,
            "memory-etag",
            len(data),
            content_type,
        )

    async def list(
        self,
        bucket: str,
        *,
        prefix: str,
    ) -> Sequence[StorageObject]:
        return [
            await self.stat(object_bucket, key)
            for object_bucket, key in self.objects
            if object_bucket == bucket and key.startswith(prefix)
        ]

    async def generate_presigned_upload(
        self,
        bucket: str,
        object_key: str,
        *,
        expires: timedelta,
    ) -> str:
        return f"https://storage.test/{bucket}/{object_key}?put={expires.seconds}"

    async def generate_presigned_download(
        self,
        bucket: str,
        object_key: str,
        *,
        expires: timedelta,
    ) -> str:
        return f"https://storage.test/{bucket}/{object_key}?get={expires.seconds}"


@pytest.fixture
def migrated_media_database(
    monkeypatch: MonkeyPatch,
    database_url: str,
) -> Iterator[None]:
    monkeypatch.chdir(BACKEND_ROOT)
    monkeypatch.setenv("FASHION_NETWORK_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        command.upgrade(Config(BACKEND_ROOT / "alembic.ini"), "head")
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def media_session(
    migrated_media_database: None,
    database_url: str,
) -> AsyncIterator[AsyncSession]:
    del migrated_media_database
    engine = create_async_engine(database_url, pool_pre_ping=True)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()
    await engine.dispose()


def _image(
    image_format: str = "PNG",
    *,
    color: tuple[int, int, int] = (20, 40, 60),
    size: tuple[int, int] = (12, 8),
) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format=image_format)
    return output.getvalue()


def _upload(
    data: bytes,
    *,
    filename: str = "store.png",
    mime_type: str = "image/png",
    display_order: int = 0,
) -> StoreMediaUpload:
    return StoreMediaUpload(
        filename=filename,
        declared_mime_type=mime_type,
        data=data,
        display_order=display_order,
    )


async def _user(session: AsyncSession, email: str) -> UUID:
    user = await SqlAlchemyUserRepository(session).add(
        UserCreate(
            email=email,
            display_name="Media Actor",
            password_hash=ARGON2_HASH,
        )
    )
    return user.id


async def _store(
    session: AsyncSession,
    events: RecordingPublisher,
    owner_id: UUID,
) -> UUID:
    store = await StoreService(
        SqlAlchemyStoreRepository(session),
        events,
        StoreValidationService(),
        StoreSlugService(),
    ).create(
        StoreCreate(
            owner_id=owner_id,
            name="Media Store",
            description=None,
            contact=StoreContact(
                phone="+91 9876543210",
                email="media@example.com",
            ),
            address=StoreAddress(
                address="12 Media Road",
                city="Imphal",
                district="Imphal West",
                state="Manipur",
                country="India",
                postal_code="795001",
            ),
        )
    )
    return store.id


def _service(
    session: AsyncSession,
    events: RecordingPublisher,
    storage: MemoryStorage,
) -> tuple[StoreMediaService, StoreMediaStorageTransaction]:
    storage_transaction = StoreMediaStorageTransaction(storage)
    return (
        StoreMediaService(
            SqlAlchemyStoreRepository(session),
            SqlAlchemyStoreMediaRepository(session),
            storage,
            storage_transaction,
            StoreMediaValidationService(),
            StoreMediaAuditService(events),
            bucket=BUCKET,
            presigned_expiration_seconds=900,
        ),
        storage_transaction,
    )


@pytest.mark.parametrize(
    ("image_format", "filename", "mime_type"),
    [
        ("JPEG", "store.jpg", "image/jpeg"),
        ("PNG", "store.png", "image/png"),
        ("WEBP", "store.webp", "image/webp"),
        ("AVIF", "store.avif", "image/avif"),
    ],
)
def test_validation_accepts_supported_decoded_images(
    image_format: str,
    filename: str,
    mime_type: str,
) -> None:
    validated = StoreMediaValidationService().validate(
        StoreMediaType.GALLERY,
        _upload(
            _image(image_format),
            filename=filename,
            mime_type=mime_type,
        ),
    )
    assert validated.mime_type == mime_type
    assert validated.width == 12
    assert validated.height == 8
    assert validated.orientation == 1
    assert str(validated.aspect_ratio) == "1.500000"


def test_validation_rejects_magic_mime_and_extension_mismatches() -> None:
    validator = StoreMediaValidationService()
    with pytest.raises(AppError):
        validator.validate(
            StoreMediaType.LOGO,
            _upload(_image(), filename="store.jpg", mime_type="image/jpeg"),
        )
    with pytest.raises(AppError):
        validator.validate(
            StoreMediaType.LOGO,
            _upload(_image(), filename="store.gif", mime_type="image/png"),
        )


def test_validation_rejects_oversize_and_checksum_mismatch() -> None:
    validator = StoreMediaValidationService()
    with pytest.raises(AppError):
        validator.validate(
            StoreMediaType.LOGO,
            _upload(b"x" * (validator.maximum_size(StoreMediaType.LOGO) + 1)),
        )
    upload = _upload(_image())
    with pytest.raises(AppError):
        validator.validate(
            StoreMediaType.LOGO,
            StoreMediaUpload(
                filename=upload.filename,
                declared_mime_type=upload.declared_mime_type,
                data=upload.data,
                declared_checksum_sha256="0" * 64,
            ),
        )


def test_filename_is_sanitized_and_never_used_as_an_object_path() -> None:
    validator = StoreMediaValidationService()
    assert validator.sanitize_filename("../../unsafe<script>.png") == (
        "unsafe_script_.png"
    )


async def test_upload_persists_trusted_metadata_key_and_safe_event(
    media_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    storage = MemoryStorage()
    owner_id = await _user(media_session, "media-upload-owner@example.com")
    store_id = await _store(media_session, events, owner_id)
    service, _ = _service(media_session, events, storage)

    media = await service.upload(
        store_id,
        owner_id,
        StoreMediaType.LOGO,
        _upload(_image(), filename="../../My Logo.png"),
    )

    assert media.id.version == 7
    assert media.object_key.startswith(f"stores/{store_id}/logos/")
    assert "My Logo" not in media.object_key
    assert media.original_filename == "My Logo.png"
    assert media.mime_type == "image/png"
    assert media.checksum_sha256
    assert await storage.exists(media.bucket, media.object_key)
    event = events.events[-1]
    assert event.event_name == "store.logo.uploaded"
    assert "checksum" not in event.payload
    assert "url" not in event.payload


async def test_logo_and_banner_replacement_archive_previous_records(
    media_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    storage = MemoryStorage()
    owner_id = await _user(media_session, "media-replace-owner@example.com")
    store_id = await _store(media_session, events, owner_id)
    service, _ = _service(media_session, events, storage)

    first_logo = await service.upload(
        store_id,
        owner_id,
        StoreMediaType.LOGO,
        _upload(_image(color=(1, 2, 3))),
    )
    second_logo = await service.upload(
        store_id,
        owner_id,
        StoreMediaType.LOGO,
        _upload(_image(color=(4, 5, 6))),
    )
    first_banner = await service.upload(
        store_id,
        owner_id,
        StoreMediaType.BANNER,
        _upload(_image(color=(7, 8, 9))),
    )
    second_banner = await service.upload(
        store_id,
        owner_id,
        StoreMediaType.BANNER,
        _upload(_image(color=(10, 11, 12))),
    )
    repository = SqlAlchemyStoreMediaRepository(media_session)

    old_logo = await repository.get(store_id, first_logo.id)
    old_banner = await repository.get(store_id, first_banner.id)
    assert old_logo is not None
    assert old_logo.status is StoreMediaStatus.ARCHIVED
    assert old_banner is not None
    assert old_banner.status is StoreMediaStatus.ARCHIVED
    assert second_logo.status is StoreMediaStatus.ACTIVE
    assert second_banner.status is StoreMediaStatus.ACTIVE


async def test_gallery_is_unlimited_and_supports_atomic_reorder(
    media_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    storage = MemoryStorage()
    owner_id = await _user(media_session, "media-gallery-owner@example.com")
    store_id = await _store(media_session, events, owner_id)
    service, _ = _service(media_session, events, storage)
    first = await service.upload(
        store_id,
        owner_id,
        StoreMediaType.GALLERY,
        _upload(_image(color=(20, 1, 1)), display_order=0),
    )
    second = await service.upload(
        store_id,
        owner_id,
        StoreMediaType.GALLERY,
        _upload(_image(color=(20, 2, 2)), display_order=1),
    )

    reordered = await service.reorder(
        store_id,
        owner_id,
        [
            StoreMediaReorderItem(first.id, 1, first.version),
            StoreMediaReorderItem(second.id, 0, second.version),
        ],
    )
    assert [item.display_order for item in reordered] == [1, 0]
    assert [event.event_name for event in events.events][-2:] == [
        "store.media.reordered",
        "store.media.reordered",
    ]


async def test_duplicate_upload_and_cross_store_access_are_rejected(
    media_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    storage = MemoryStorage()
    owner_id = await _user(media_session, "media-duplicate-owner@example.com")
    other_id = await _user(media_session, "media-duplicate-other@example.com")
    store_id = await _store(media_session, events, owner_id)
    service, _ = _service(media_session, events, storage)
    data = _image()
    await service.upload(
        store_id,
        owner_id,
        StoreMediaType.GALLERY,
        _upload(data),
    )
    with pytest.raises(AppError) as duplicate:
        await service.upload(
            store_id,
            owner_id,
            StoreMediaType.GALLERY,
            _upload(data),
        )
    assert duplicate.value.status_code == 409
    with pytest.raises(AppError) as hidden:
        await service.list(store_id, other_id, offset=0, limit=25)
    assert hidden.value.status_code == 404


async def test_metadata_update_uses_optimistic_version(
    media_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    storage = MemoryStorage()
    owner_id = await _user(media_session, "media-update-owner@example.com")
    store_id = await _store(media_session, events, owner_id)
    service, _ = _service(media_session, events, storage)
    media = await service.upload(
        store_id,
        owner_id,
        StoreMediaType.GALLERY,
        _upload(_image()),
    )
    updated = await service.update(
        store_id,
        media.id,
        owner_id,
        StoreMediaUpdate(media.version, display_order=4, is_public=True),
    )
    assert updated.display_order == 4
    assert updated.is_public is True
    with pytest.raises(AppError) as stale:
        await service.update(
            store_id,
            media.id,
            owner_id,
            StoreMediaUpdate(media.version, display_order=5),
        )
    assert stale.value.status_code == 409


async def test_soft_delete_removes_object_after_storage_commit(
    media_session: AsyncSession,
) -> None:
    events = RecordingPublisher()
    storage = MemoryStorage()
    owner_id = await _user(media_session, "media-delete-owner@example.com")
    store_id = await _store(media_session, events, owner_id)
    service, transaction = _service(media_session, events, storage)
    media = await service.upload(
        store_id,
        owner_id,
        StoreMediaType.GALLERY,
        _upload(_image()),
    )

    await service.delete(store_id, media.id, owner_id)
    assert not await storage.exists(media.bucket, media.object_key)
    await transaction.commit()
    persisted = await SqlAlchemyStoreMediaRepository(media_session).get(
        store_id,
        media.id,
        include_deleted=True,
    )
    assert persisted is not None
    assert persisted.status is StoreMediaStatus.DELETED
    assert persisted.deleted_at is not None
    assert events.events[-1].event_name == "store.media.deleted"


async def test_storage_transaction_rolls_back_upload_and_staged_delete() -> None:
    storage = MemoryStorage()
    transaction = StoreMediaStorageTransaction(storage)
    first = await transaction.upload(
        BUCKET,
        "stores/rollback/gallery/first.png",
        b"first",
        content_type="image/png",
    )
    await transaction.stage_delete(first.bucket, first.object_key)
    await transaction.rollback()
    assert not await storage.list(BUCKET, prefix="stores/rollback/")

    await storage.upload(
        BUCKET,
        "stores/rollback/gallery/existing.png",
        b"existing",
        content_type="image/png",
    )
    second = StoreMediaStorageTransaction(storage)
    await second.stage_delete(
        BUCKET,
        "stores/rollback/gallery/existing.png",
    )
    await second.rollback()
    assert await storage.exists(
        BUCKET,
        "stores/rollback/gallery/existing.png",
    )


async def test_repository_schema_indexes_and_soft_delete_filter(
    media_session: AsyncSession,
    database_url: str,
) -> None:
    events = RecordingPublisher()
    storage = MemoryStorage()
    owner_id = await _user(media_session, "media-index-owner@example.com")
    store_id = await _store(media_session, events, owner_id)
    service, _ = _service(media_session, events, storage)
    media = await service.upload(
        store_id,
        owner_id,
        StoreMediaType.GALLERY,
        _upload(_image()),
    )
    await service.delete(store_id, media.id, owner_id)
    assert (
        await SqlAlchemyStoreMediaRepository(media_session).get(
            store_id,
            media.id,
        )
        is None
    )

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            indexes = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_indexes(
                    "store_media"
                )
            )
            columns = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_columns(
                    "store_media"
                )
            )
    finally:
        await engine.dispose()
    assert {index["name"] for index in indexes} >= {
        "ix_store_media_store_id",
        "ix_store_media_media_type",
        "ix_store_media_display_order",
        "ix_store_media_status",
        "ix_store_media_uploaded_by",
        "ix_store_media_not_deleted",
        "uq_store_media_active_logo",
        "uq_store_media_active_banner",
        "uq_store_media_checksum",
    }
    assert "download_url" not in {column["name"] for column in columns}


def test_media_openapi_documents_all_routes_and_permissions(
    test_settings: Settings,
) -> None:
    application = FastAPI()
    application.include_router(media_router, prefix="/api/v1")
    install_custom_openapi(application, test_settings)
    schema = application.openapi()
    base = "/api/v1/stores/{store_id}/media"
    expected = {
        ("post", f"{base}/logo", "store:update"),
        ("post", f"{base}/banner", "store:update"),
        ("post", f"{base}/gallery", "store:update"),
        ("get", base, "store:view"),
        ("get", f"{base}/{{media_id}}", "store:view"),
        ("patch", f"{base}/{{media_id}}", "store:update"),
        ("delete", f"{base}/{{media_id}}", "store:delete"),
        ("post", f"{base}/reorder", "store:update"),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]


def test_store_media_metrics_are_low_cardinality() -> None:
    exposition = generate_latest().decode()
    for metric in (
        "fashion_network_store_media_upload_total",
        "fashion_network_store_media_delete_total",
        "fashion_network_store_media_bytes_total",
        "fashion_network_store_media_failures_total",
    ):
        assert metric in exposition
        line = next(
            value for value in exposition.splitlines() if value.startswith(metric)
        )
        assert "{" not in line


async def test_minio_adapter_upload_download_copy_move_list_and_presign() -> None:
    provider = MinIOStorageProvider(
        "http://localhost:9000",
        "fashion_network",
        "fashion_network_dev_minio_secret",
    )
    prefix = f"stores/minio-contract-{uuid4()}/gallery"
    original = f"{prefix}/original.png"
    copied = f"{prefix}/copied.png"
    moved = f"{prefix}/moved.png"
    data = _image()
    try:
        uploaded = await provider.upload(
            BUCKET,
            original,
            data,
            content_type="image/png",
        )
        assert uploaded.size == len(data)
        assert await provider.download(BUCKET, original) == data
        assert await provider.exists(BUCKET, original)
        assert (await provider.stat(BUCKET, original)).etag
        await provider.copy(BUCKET, original, BUCKET, copied)
        await provider.move(BUCKET, copied, BUCKET, moved)
        assert not await provider.exists(BUCKET, copied)
        assert {
            item.object_key
            for item in await provider.list(
                BUCKET,
                prefix=prefix,
            )
        } >= {original, moved}
        upload_url = await provider.generate_presigned_upload(
            BUCKET,
            f"{prefix}/presigned.png",
            expires=timedelta(minutes=15),
        )
        download_url = await provider.generate_presigned_download(
            BUCKET,
            original,
            expires=timedelta(minutes=15),
        )
        assert "X-Amz-Expires=900" in upload_url
        assert "X-Amz-Expires=900" in download_url
    finally:
        await provider.delete(BUCKET, original)
        await provider.delete(BUCKET, copied)
        await provider.delete(BUCKET, moved)
