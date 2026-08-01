from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.common.pagination import PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.stores.api.dependencies import StoreSearchServiceDependency
from app.modules.stores.api.search_schemas import (
    SearchRebuildResponse,
    StoreAutocompleteItemResponse,
    StoreAutocompleteResponse,
    StoreSearchResponse,
    StoreSearchResultResponse,
)
from app.modules.stores.domain.search import (
    StoreAutocompleteItem,
    StoreSearchDocument,
)

router = APIRouter(prefix="/stores/search", tags=["Store Search"])


def _result(
    document: StoreSearchDocument,
    score: float | None = None,
) -> StoreSearchResultResponse:
    return StoreSearchResultResponse(
        store_id=document.store_id,
        name=document.name,
        slug=document.slug,
        description=document.description,
        category=document.category,
        city=document.city,
        state=document.state,
        country=document.country,
        postal_code=document.postal_code,
        latitude=document.latitude,
        longitude=document.longitude,
        verified=document.verified,
        active=document.active,
        currently_open=document.currently_open,
        logo_exists=document.logo_exists,
        banner_exists=document.banner_exists,
        media_count=document.media_count,
        created_at=document.created_at,
        updated_at=document.updated_at,
        score=score,
    )


def _autocomplete(value: StoreAutocompleteItem) -> StoreAutocompleteItemResponse:
    return StoreAutocompleteItemResponse(
        store_id=value.store_id,
        name=value.name,
        slug=value.slug,
    )


@router.get(
    "",
    response_model=StoreSearchResponse,
    summary="Search public Stores",
    description=(
        "Searches only verified, active, non-deleted Store projections. Supports "
        "text, filters, pagination, sorting, and Meilisearch native geo search."
    ),
    responses={503: {"description": "Search provider unavailable"}},
)
async def search_stores(
    service: StoreSearchServiceDependency,
    query: str = "",
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    category: str | None = None,
    verified: bool | None = None,
    currently_open: bool | None = None,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius: Annotated[int | None, Query(gt=0)] = None,
    sort: str = "relevance",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> StoreSearchResponse:
    filters = {
        key: value
        for key, value in {
            "city": city,
            "state": state,
            "country": country,
            "category": category,
            "verified": verified,
            "currently_open": currently_open,
        }.items()
        if value is not None
    }
    page = await service.search(
        query=query,
        filters=filters,
        sort=sort,
        latitude=latitude,
        longitude=longitude,
        radius=radius,
        offset=offset,
        limit=limit,
    )
    return StoreSearchResponse(
        items=[_result(item.document, item.score) for item in page.items],
        page=PageMetadata(
            has_more=offset + len(page.items) < page.total,
            limit=limit,
            total=page.total,
            offset=offset,
        ),
        processing_time_ms=page.processing_time_ms,
    )


@router.get(
    "/autocomplete",
    response_model=StoreAutocompleteResponse,
    summary="Autocomplete public Store names",
    description="Returns top-ranked public Store name, slug, and ID matches.",
)
async def autocomplete_stores(
    service: StoreSearchServiceDependency,
    query: str,
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> StoreAutocompleteResponse:
    values = await service.autocomplete(query=query, limit=limit)
    return StoreAutocompleteResponse(items=[_autocomplete(item) for item in values])


@router.post(
    "/rebuild",
    response_model=SearchRebuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a complete Store search rebuild",
    description="Queues an asynchronous PostgreSQL-to-Meilisearch rebuild.",
    dependencies=[require_permission("system:manage")],
)
async def rebuild_stores() -> SearchRebuildResponse:
    from app.worker import celery_app

    result = celery_app.send_task("stores.search.rebuild")
    return SearchRebuildResponse(task_id=str(result.id), status="queued")
