from collections.abc import Mapping
from typing import Any

from httpx import AsyncClient, Response


async def api_get(client: AsyncClient, path: str, **kwargs: Any) -> Response:
    return await client.get(path, **kwargs)


async def api_post(
    client: AsyncClient, path: str, payload: Mapping[str, object], **kwargs: Any
) -> Response:
    return await client.post(path, json=dict(payload), **kwargs)


async def api_patch(
    client: AsyncClient, path: str, payload: Mapping[str, object], **kwargs: Any
) -> Response:
    return await client.patch(path, json=dict(payload), **kwargs)


async def api_delete(client: AsyncClient, path: str, **kwargs: Any) -> Response:
    return await client.delete(path, **kwargs)
