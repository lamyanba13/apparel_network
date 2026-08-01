from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi import FastAPI

from app.common.api import install_custom_openapi
from app.common.exceptions import AppError
from app.common.utils import generate_uuid7
from app.core.config import Settings
from app.modules.stores.api.search_router import router as search_router
from app.modules.stores.application.search_services import StoreSearchService
from app.modules.stores.domain.search import (
    StoreAutocompleteItem,
    StoreSearchDocument,
    StoreSearchPage,
    StoreSearchResult,
)
from app.modules.stores.domain.search_events import (
    StoreIndexed,
    StoreRemovedFromSearch,
    StoreSearchRebuilt,
    StoreSearchSyncRequested,
    StoreUpdatedInSearch,
)
from app.modules.stores.infrastructure.events import StoreEventPublisher
from app.modules.stores.infrastructure.search_repository import (
    MeilisearchStoreRepository,
    _sort_value,
)

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def _document() -> StoreSearchDocument:
    return StoreSearchDocument(
        store_id=UUID(int=1),
        name="Imphal Fashion",
        slug="imphal-fashion",
        description="A public clothing store",
        category=None,
        city="Imphal",
        state="Manipur",
        country="India",
        postal_code="795001",
        latitude=Decimal("24.817"),
        longitude=Decimal("93.9368"),
        verified=True,
        active=True,
        currently_open=True,
        logo_exists=True,
        banner_exists=False,
        media_count=3,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeSearchRepository:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []
        self.autocomplete_calls: list[dict[str, object]] = []
        self.page = StoreSearchPage(
            items=(StoreSearchResult(document=_document()),),
            total=1,
            limit=25,
            offset=0,
            processing_time_ms=2,
        )

    async def search(self, **kwargs: object) -> StoreSearchPage:
        self.search_calls.append(kwargs)
        return self.page

    async def autocomplete(self, **kwargs: object) -> list[StoreAutocompleteItem]:
        self.autocomplete_calls.append(kwargs)
        return [
            StoreAutocompleteItem(
                store_id=UUID(int=1),
                name="Imphal Fashion",
                slug="imphal-fashion",
            )
        ]


async def test_search_normalizes_filters_pagination_and_sorting() -> None:
    repository = FakeSearchRepository()
    service = StoreSearchService(repository)

    page = await service.search(
        query="  imphal   fashion ",
        filters={"city": "Imphal", "verified": True},
        sort="alphabetical",
        latitude=None,
        longitude=None,
        radius=None,
        limit=10,
        offset=20,
    )

    assert page.total == 1
    assert repository.search_calls[0]["query"] == "imphal fashion"
    assert repository.search_calls[0]["filters"] == {
        "city": "Imphal",
        "verified": True,
    }
    assert repository.search_calls[0]["offset"] == 20


async def test_autocomplete_returns_top_ranked_public_fields() -> None:
    repository = FakeSearchRepository()
    values = await StoreSearchService(repository).autocomplete(query="im", limit=5)

    assert values[0].name == "Imphal Fashion"
    assert {field.name for field in fields(values[0])} == {
        "store_id",
        "name",
        "slug",
    }


@pytest.mark.parametrize(
    ("sort", "latitude", "longitude", "expected"),
    [
        ("relevance", None, None, None),
        ("alphabetical", None, None, "name:asc"),
        ("newest", None, None, "created_at:desc"),
        ("recently_updated", None, None, "updated_at:desc"),
        ("nearest", 24.8, 93.9, "_geoPoint(24.8, 93.9):asc"),
    ],
)
def test_sort_translation(
    sort: str,
    latitude: float | None,
    longitude: float | None,
    expected: str | None,
) -> None:
    assert _sort_value(sort, latitude, longitude) == expected


@pytest.mark.parametrize(
    "filters",
    [
        {"unknown": "value"},
        {"owner_id": "private"},
        {"email": "private@example.com"},
    ],
)
def test_unknown_or_private_filters_are_rejected(
    filters: dict[str, object],
) -> None:
    with pytest.raises(AppError) as error:
        StoreSearchService.validate_filters(filters)
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    ("sort", "latitude", "longitude", "radius"),
    [
        ("nearest", None, None, None),
        ("relevance", 100.0, 20.0, None),
        ("relevance", 20.0, 200.0, None),
        ("relevance", 20.0, 20.0, 0),
        ("relevance", 20.0, None, None),
    ],
)
def test_geo_validation_rejects_invalid_requests(
    sort: str,
    latitude: float | None,
    longitude: float | None,
    radius: int | None,
) -> None:
    with pytest.raises(AppError) as error:
        StoreSearchService.validate_geo(sort, latitude, longitude, radius)
    assert error.value.status_code == 422


def test_query_length_is_bounded() -> None:
    with pytest.raises(AppError):
        StoreSearchService.normalize_query("x" * 201)


def test_public_document_has_no_private_fields() -> None:
    public = _document().public_dict()

    assert set(public) == {
        "store_id",
        "name",
        "slug",
        "description",
        "category",
        "city",
        "state",
        "country",
        "postal_code",
        "latitude",
        "longitude",
        "verified",
        "active",
        "currently_open",
        "logo_exists",
        "banner_exists",
        "media_count",
        "created_at",
        "updated_at",
        "_geo",
    }
    assert "owner_id" not in public
    assert "email" not in public
    assert "phone" not in public


def test_search_event_payloads_are_safe() -> None:
    kwargs = {"store_id": UUID(int=1), "operation": "update"}
    for event_type in (
        StoreSearchSyncRequested,
        StoreIndexed,
        StoreUpdatedInSearch,
        StoreRemovedFromSearch,
        StoreSearchRebuilt,
    ):
        event = event_type(**kwargs)
        assert set(event.payload) == {"store_id", "operation"}


@pytest.mark.parametrize(
    ("source_name", "operation"),
    [
        ("store.created", "index"),
        ("store.updated", "update"),
        ("store.verified", "index"),
        ("store.closed", "delete"),
        ("store.logo.uploaded", "update"),
        ("store.banner.uploaded", "update"),
        ("store.gallery.uploaded", "update"),
        ("store.media.deleted", "update"),
        ("store.hours.updated", "update"),
    ],
)
async def test_store_events_dispatch_search_sync_requests(
    source_name: str,
    operation: str,
) -> None:
    requests: list[StoreSearchSyncRequested] = []

    def dispatch(event: StoreSearchSyncRequested) -> None:
        requests.append(event)

    await StoreEventPublisher(dispatcher=dispatch).publish(
        _SourceEvent(source_name, UUID(int=1))
    )

    assert requests[0].operation == operation
    assert requests[0].store_id == UUID(int=1)


async def test_unrelated_store_event_is_not_dispatched() -> None:
    requests: list[StoreSearchSyncRequested] = []

    await StoreEventPublisher(dispatcher=requests.append).publish(
        _SourceEvent("store.submitted", UUID(int=1))
    )

    assert requests == []


def test_openapi_documents_public_search_and_admin_rebuild(
    test_settings: Settings,
) -> None:
    application = FastAPI()
    application.include_router(search_router, prefix="/api/v1")
    install_custom_openapi(application, test_settings)
    schema = application.openapi()

    assert "security" not in schema["paths"]["/api/v1/stores/search"]["get"]
    assert (
        "security" not in schema["paths"]["/api/v1/stores/search/autocomplete"]["get"]
    )
    rebuild = schema["paths"]["/api/v1/stores/search/rebuild"]["post"]
    assert rebuild["x-authorization"] == [
        {"kind": "permission", "values": ["system:manage"]}
    ]


def test_meilisearch_repository_uses_stores_index_and_settings(
    test_settings: Settings,
) -> None:
    repository = MeilisearchStoreRepository(test_settings)

    assert repository.index_name == "stores"
    assert repository._base_url == test_settings.meilisearch_url


def test_search_sync_event_is_domain_event() -> None:
    event = StoreSearchSyncRequested(store_id=UUID(int=2), operation="index")

    assert event.event_id.version == 7
    assert event.occurred_at.tzinfo is not None


class _SourceEvent:
    schema_version = 1
    correlation_id = None

    def __init__(self, event_name: str, store_id: UUID) -> None:
        self.event_name = event_name
        self.event_id = generate_uuid7()
        self.occurred_at = NOW
        self.payload = {"store_id": str(store_id)}
