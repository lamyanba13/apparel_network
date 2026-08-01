from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

import httpx

from app.core.config import Settings
from app.modules.stores.application.search_repositories import StoreSearchRepository
from app.modules.stores.domain.search import (
    StoreAutocompleteItem,
    StoreSearchDocument,
    StoreSearchPage,
    StoreSearchResult,
)


class SearchProviderError(RuntimeError):
    pass


class MeilisearchStoreRepository(StoreSearchRepository):
    index_name = "stores"

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.meilisearch_url.rstrip("/")
        self._headers = (
            {
                "Authorization": (
                    f"Bearer {settings.meilisearch_master_key.get_secret_value()}"
                )
            }
            if settings.meilisearch_master_key is not None
            else {}
        )

    async def search(
        self,
        *,
        query: str,
        filters: Mapping[str, object],
        sort: str,
        latitude: float | None,
        longitude: float | None,
        radius: int | None,
        limit: int,
        offset: int,
    ) -> StoreSearchPage:
        filter_values = ["verified = true", "active = true"]
        filter_values.extend(
            _filter_expression(key, value) for key, value in filters.items()
        )
        if latitude is not None and longitude is not None and radius is not None:
            filter_values.append(f"_geoRadius({latitude}, {longitude}, {radius})")
        payload: dict[str, object] = {
            "q": query,
            "filter": " AND ".join(filter_values),
            "limit": limit,
            "offset": offset,
        }
        sort_value = _sort_value(sort, latitude, longitude)
        if sort_value is not None:
            payload["sort"] = [sort_value]
        data = await self._request("POST", "/search", json=payload)
        return _page(data)

    async def autocomplete(
        self,
        *,
        query: str,
        limit: int,
    ) -> Sequence[StoreAutocompleteItem]:
        data = await self._request(
            "POST",
            "/search",
            json={
                "q": query,
                "filter": "verified = true AND active = true",
                "limit": limit,
                "attributesToRetrieve": ["store_id", "name", "slug"],
            },
        )
        return [
            StoreAutocompleteItem(
                store_id=UUID(str(item["store_id"])),
                name=str(item["name"]),
                slug=str(item["slug"]),
            )
            for item in data.get("hits", [])
        ]

    async def index_store(self, document: StoreSearchDocument) -> None:
        await self._request("POST", "/documents", json=[document.public_dict()])

    async def update_store(self, document: StoreSearchDocument) -> None:
        await self.index_store(document)

    async def delete_store(self, store_id: UUID) -> None:
        await self._request("DELETE", f"/documents/{store_id}")

    async def bulk_rebuild(self, documents: Sequence[StoreSearchDocument]) -> None:
        for start in range(0, len(documents), 500):
            await self._request(
                "POST",
                "/documents",
                json=[
                    document.public_dict()
                    for document in documents[start : start + 500]
                ],
            )

    async def configure_index(self) -> None:
        try:
            await self._request("GET", "")
        except SearchProviderError:
            task = await self._request_index_collection(
                "POST", json={"uid": self.index_name}
            )
            task_uid = task.get("taskUid")
            if isinstance(task_uid, int):
                await self._wait_for_task(task_uid)
        await self._request(
            "PATCH",
            "/settings",
            json={
                "searchableAttributes": [
                    "name",
                    "description",
                    "category",
                    "city",
                    "state",
                    "country",
                ],
                "filterableAttributes": [
                    "verified",
                    "active",
                    "category",
                    "city",
                    "state",
                    "country",
                    "currently_open",
                ],
                "sortableAttributes": ["created_at", "updated_at", "name", "_geo"],
                "distinctAttribute": "store_id",
            },
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self._base_url}/indexes/{self.index_name}{path}"
        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=httpx.Timeout(15.0),
            ) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                if not response.content:
                    return {}
                value = response.json()
                return value if isinstance(value, dict) else {}
        except (httpx.HTTPError, ValueError) as error:
            raise SearchProviderError("Meilisearch operation failed") from error

    async def _request_index_collection(
        self, method: str, **kwargs: Any
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=httpx.Timeout(15.0),
            ) as client:
                response = await client.request(
                    method, f"{self._base_url}/indexes", **kwargs
                )
                response.raise_for_status()
                if not response.content:
                    return {}
                value = response.json()
                return value if isinstance(value, dict) else {}
        except (httpx.HTTPError, ValueError) as error:
            raise SearchProviderError("Meilisearch operation failed") from error

    async def _wait_for_task(self, task_uid: int) -> None:
        for _ in range(30):
            task = await self._request_root("GET", f"/tasks/{task_uid}")
            status = task.get("status")
            if status == "succeeded":
                return
            if status in {"failed", "canceled"}:
                raise SearchProviderError("Meilisearch index task failed")
            await asyncio.sleep(0.1)
        raise SearchProviderError("Meilisearch index task timed out")

    async def _request_root(
        self, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=httpx.Timeout(15.0),
            ) as client:
                response = await client.request(
                    method, f"{self._base_url}{path}", **kwargs
                )
                response.raise_for_status()
                if not response.content:
                    return {}
                value = response.json()
                return value if isinstance(value, dict) else {}
        except (httpx.HTTPError, ValueError) as error:
            raise SearchProviderError("Meilisearch operation failed") from error


def _page(data: Mapping[str, Any]) -> StoreSearchPage:
    items = [StoreSearchResult(document=_document(raw)) for raw in data.get("hits", [])]
    return StoreSearchPage(
        items=tuple(items),
        total=int(data.get("estimatedTotalHits", data.get("totalHits", 0))),
        limit=int(data.get("limit", len(items))),
        offset=int(data.get("offset", 0)),
        processing_time_ms=(
            int(data["processingTimeMs"]) if "processingTimeMs" in data else None
        ),
    )


def _document(raw: Mapping[str, Any]) -> StoreSearchDocument:
    from datetime import datetime
    from decimal import Decimal

    return StoreSearchDocument(
        store_id=UUID(str(raw["store_id"])),
        name=str(raw["name"]),
        slug=str(raw["slug"]),
        description=raw.get("description"),
        category=raw.get("category"),
        city=str(raw["city"]),
        state=str(raw["state"]),
        country=str(raw["country"]),
        postal_code=str(raw["postal_code"]),
        latitude=(
            Decimal(str(raw["latitude"])) if raw.get("latitude") is not None else None
        ),
        longitude=(
            Decimal(str(raw["longitude"])) if raw.get("longitude") is not None else None
        ),
        verified=bool(raw["verified"]),
        active=bool(raw["active"]),
        currently_open=bool(raw["currently_open"]),
        logo_exists=bool(raw["logo_exists"]),
        banner_exists=bool(raw["banner_exists"]),
        media_count=int(raw["media_count"]),
        created_at=datetime.fromisoformat(str(raw["created_at"])),
        updated_at=datetime.fromisoformat(str(raw["updated_at"])),
    )


def _sort_value(
    sort: str,
    latitude: float | None,
    longitude: float | None,
) -> str | None:
    if sort == "alphabetical":
        return "name:asc"
    if sort == "newest":
        return "created_at:desc"
    if sort == "recently_updated":
        return "updated_at:desc"
    if sort == "nearest" and latitude is not None and longitude is not None:
        return f"_geoPoint({latitude}, {longitude}):asc"
    return None


def _escape_filter(value: str) -> str:
    return value.replace('"', '\\"')


def _filter_expression(key: str, value: object) -> str:
    if isinstance(value, bool):
        return f"{key} = {'true' if value else 'false'}"
    return f'{key} = "{_escape_filter(str(value))}"'
