from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import timedelta
from functools import partial
from io import BytesIO
from urllib.parse import urlsplit

from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error

from app.modules.stores.application.media_storage import (
    StorageError,
    StorageObject,
    StorageProvider,
)


class MinIOStorageProvider(StorageProvider):
    """S3-compatible object operations used by local MinIO and production R2."""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        *,
        region: str | None = None,
    ) -> None:
        endpoint = urlsplit(endpoint_url)
        if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
            raise ValueError("Storage endpoint must be an HTTP(S) URL.")
        if endpoint.path not in {"", "/"}:
            raise ValueError("Storage endpoint cannot contain a path.")
        self._client = Minio(
            endpoint.netloc,
            access_key=access_key,
            secret_key=secret_key,
            secure=endpoint.scheme == "https",
            region=region,
        )

    async def upload(
        self,
        bucket: str,
        object_key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> StorageObject:
        try:
            result = await asyncio.to_thread(
                self._client.put_object,
                bucket,
                object_key,
                BytesIO(data),
                len(data),
                content_type=content_type,
            )
            return StorageObject(
                bucket=bucket,
                object_key=object_key,
                etag=_etag(result.etag),
                size=len(data),
                content_type=content_type,
            )
        except S3Error as error:
            raise StorageError("Object upload failed.") from error

    async def download(self, bucket: str, object_key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                bucket,
                object_key,
            )
            try:
                return await asyncio.to_thread(response.read)
            finally:
                response.close()
                response.release_conn()
        except S3Error as error:
            raise StorageError("Object download failed.") from error

    async def delete(self, bucket: str, object_key: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.remove_object,
                bucket,
                object_key,
            )
        except S3Error as error:
            raise StorageError("Object deletion failed.") from error

    async def copy(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> StorageObject:
        try:
            result = await asyncio.to_thread(
                self._client.copy_object,
                destination_bucket,
                destination_key,
                CopySource(source_bucket, source_key),
            )
            copied = await self.stat(destination_bucket, destination_key)
            return StorageObject(
                bucket=copied.bucket,
                object_key=copied.object_key,
                etag=_etag(result.etag),
                size=copied.size,
                content_type=copied.content_type,
            )
        except S3Error as error:
            raise StorageError("Object copy failed.") from error

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
        try:
            await self.delete(source_bucket, source_key)
        except StorageError:
            await self.delete(destination_bucket, destination_key)
            raise
        return copied

    async def exists(self, bucket: str, object_key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._client.stat_object,
                bucket,
                object_key,
            )
            return True
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject"}:
                return False
            raise StorageError("Object existence check failed.") from error

    async def stat(self, bucket: str, object_key: str) -> StorageObject:
        try:
            result = await asyncio.to_thread(
                self._client.stat_object,
                bucket,
                object_key,
            )
            return StorageObject(
                bucket=bucket,
                object_key=object_key,
                etag=_etag(result.etag),
                size=int(result.size or 0),
                content_type=result.content_type,
            )
        except S3Error as error:
            raise StorageError("Object metadata lookup failed.") from error

    async def list(
        self,
        bucket: str,
        *,
        prefix: str,
    ) -> Sequence[StorageObject]:
        try:
            objects = await asyncio.to_thread(
                lambda: list(
                    self._client.list_objects(
                        bucket,
                        prefix=prefix,
                        recursive=True,
                    )
                )
            )
            return [
                StorageObject(
                    bucket=bucket,
                    object_key=value.object_name,
                    etag=_etag(value.etag),
                    size=int(value.size or 0),
                )
                for value in objects
            ]
        except S3Error as error:
            raise StorageError("Object listing failed.") from error

    async def generate_presigned_upload(
        self,
        bucket: str,
        object_key: str,
        *,
        expires: timedelta,
    ) -> str:
        try:
            return await asyncio.to_thread(
                partial(
                    self._client.presigned_put_object,
                    bucket,
                    object_key,
                    expires=expires,
                )
            )
        except S3Error as error:
            raise StorageError("Presigned upload generation failed.") from error

    async def generate_presigned_download(
        self,
        bucket: str,
        object_key: str,
        *,
        expires: timedelta,
    ) -> str:
        try:
            return await asyncio.to_thread(
                partial(
                    self._client.presigned_get_object,
                    bucket,
                    object_key,
                    expires=expires,
                )
            )
        except S3Error as error:
            raise StorageError("Presigned download generation failed.") from error


def _etag(value: str | None) -> str:
    return (value or "").strip('"')
