from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.common.errors import ErrorCode, FieldError
from app.common.exceptions import AppError
from app.modules.stores.application.search_repositories import StoreSearchRepository
from app.modules.stores.domain.search import (
    StoreAutocompleteItem,
    StoreSearchPage,
)
from app.observability.metrics import (
    STORE_SEARCH_FAILURES,
    STORE_SEARCH_QUERIES,
    STORE_SEARCH_RESULTS,
)

_SORTS = {"relevance", "alphabetical", "newest", "recently_updated", "nearest"}
_FILTERS = {"city", "state", "country", "category", "verified", "currently_open"}


class StoreSearchService:
    def __init__(self, repository: StoreSearchRepository) -> None:
        self._repository = repository

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
        normalized_query = self.normalize_query(query)
        normalized_sort = self.normalize_sort(sort)
        self.validate_geo(normalized_sort, latitude, longitude, radius)
        try:
            page = await self._repository.search(
                query=normalized_query,
                filters=self.validate_filters(filters),
                sort=normalized_sort,
                latitude=latitude,
                longitude=longitude,
                radius=radius,
                limit=limit,
                offset=offset,
            )
        except Exception as error:
            STORE_SEARCH_FAILURES.inc()
            raise _unavailable() from error
        STORE_SEARCH_QUERIES.inc()
        STORE_SEARCH_RESULTS.inc(len(page.items))
        return page

    async def autocomplete(
        self,
        *,
        query: str,
        limit: int,
    ) -> Sequence[StoreAutocompleteItem]:
        normalized_query = self.normalize_query(query)
        try:
            values = await self._repository.autocomplete(
                query=normalized_query,
                limit=limit,
            )
        except Exception as error:
            STORE_SEARCH_FAILURES.inc()
            raise _unavailable() from error
        STORE_SEARCH_QUERIES.inc()
        STORE_SEARCH_RESULTS.inc(len(values))
        return values

    @staticmethod
    def normalize_query(query: str) -> str:
        normalized = " ".join(query.split())
        if len(normalized) > 200:
            raise _validation("query", "Search query cannot exceed 200 characters.")
        return normalized

    @staticmethod
    def normalize_sort(sort: str) -> str:
        normalized = sort.strip().lower()
        if normalized not in _SORTS:
            raise _validation("sort", "Unsupported Store search sort.")
        return normalized

    @staticmethod
    def validate_filters(filters: Mapping[str, object]) -> Mapping[str, object]:
        unknown = set(filters) - _FILTERS
        if unknown:
            raise _validation("filters", "Unsupported Store search filter.")
        return filters

    @staticmethod
    def validate_geo(
        sort: str,
        latitude: float | None,
        longitude: float | None,
        radius: int | None,
    ) -> None:
        if sort == "nearest" and (latitude is None or longitude is None):
            raise _validation(
                "latitude",
                "Nearest sorting requires latitude and longitude.",
            )
        if (latitude is None) != (longitude is None):
            raise _validation(
                "latitude", "Latitude and longitude are required together."
            )
        if latitude is not None and not -90 <= latitude <= 90:
            raise _validation("latitude", "Latitude must be between -90 and 90.")
        if longitude is not None and not -180 <= longitude <= 180:
            raise _validation("longitude", "Longitude must be between -180 and 180.")
        if radius is not None and radius <= 0:
            raise _validation("radius", "Radius must be positive.")


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Store search validation failed",
        detail="One or more Store search fields are invalid.",
        status_code=422,
        errors=[FieldError(field=field, code="invalid_store_search", message=message)],
    )


def _unavailable() -> AppError:
    return AppError(
        code=ErrorCode.INTERNAL_SERVER_ERROR,
        title="Store search unavailable",
        detail="Store search is temporarily unavailable.",
        status_code=503,
    )
