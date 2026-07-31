from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StorageObject:
    bucket: str
    object_key: str
    etag: str
    size: int
    content_type: str | None = None


class StorageProvider(Protocol):
    async def upload(
        self,
        bucket: str,
        object_key: str,
        data: bytes,
        *,
        content_type: str,
    ) -> StorageObject: ...

    async def download(self, bucket: str, object_key: str) -> bytes: ...

    async def delete(self, bucket: str, object_key: str) -> None: ...

    async def copy(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> StorageObject: ...

    async def move(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> StorageObject: ...

    async def exists(self, bucket: str, object_key: str) -> bool: ...

    async def stat(self, bucket: str, object_key: str) -> StorageObject: ...

    async def list(
        self,
        bucket: str,
        *,
        prefix: str,
    ) -> Sequence[StorageObject]: ...

    async def generate_presigned_upload(
        self,
        bucket: str,
        object_key: str,
        *,
        expires: timedelta,
    ) -> str: ...

    async def generate_presigned_download(
        self,
        bucket: str,
        object_key: str,
        *,
        expires: timedelta,
    ) -> str: ...


class StorageError(RuntimeError):
    """Provider-neutral object storage failure without credential details."""
