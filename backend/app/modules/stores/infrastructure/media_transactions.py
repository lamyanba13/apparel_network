from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.modules.stores.application.media_storage import (
    StorageObject,
    StorageProvider,
)


@dataclass(frozen=True, slots=True)
class _UploadedObject:
    bucket: str
    object_key: str


@dataclass(frozen=True, slots=True)
class _StagedDeletion:
    bucket: str
    object_key: str
    tombstone_key: str


class StoreMediaStorageTransaction:
    """Compensate object mutations around the database-owned transaction."""

    def __init__(self, storage: StorageProvider) -> None:
        self._storage = storage
        self._uploads: list[_UploadedObject] = []
        self._deletions: list[_StagedDeletion] = []

    async def upload(
        self,
        bucket: str,
        object_key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> StorageObject:
        result = await self._storage.upload(
            bucket,
            object_key,
            data,
            content_type=content_type,
        )
        self._uploads.append(_UploadedObject(bucket, object_key))
        return result

    async def stage_delete(self, bucket: str, object_key: str) -> None:
        tombstone_key = f"{object_key}.deleted-{uuid4().hex}"
        await self._storage.move(
            bucket,
            object_key,
            bucket,
            tombstone_key,
        )
        self._deletions.append(_StagedDeletion(bucket, object_key, tombstone_key))

    async def commit(self) -> None:
        for deletion in self._deletions:
            await self._storage.delete(deletion.bucket, deletion.tombstone_key)
        self._uploads.clear()
        self._deletions.clear()

    async def rollback(self) -> None:
        for deletion in reversed(self._deletions):
            if await self._storage.exists(
                deletion.bucket,
                deletion.tombstone_key,
            ):
                await self._storage.move(
                    deletion.bucket,
                    deletion.tombstone_key,
                    deletion.bucket,
                    deletion.object_key,
                )
        for upload in reversed(self._uploads):
            if await self._storage.exists(upload.bucket, upload.object_key):
                await self._storage.delete(upload.bucket, upload.object_key)
        self._uploads.clear()
        self._deletions.clear()
