import pytest
from pydantic import ValidationError

from app.common.enums import SortDirection
from app.common.pagination import (
    CursorPagination,
    FilterParameters,
    OffsetPagination,
    PageMetadata,
    parse_sort,
)


def test_pagination_defaults_and_bounds() -> None:
    assert OffsetPagination().model_dump() == {"offset": 0, "limit": 25}
    assert CursorPagination().model_dump() == {"cursor": None, "limit": 25}
    assert PageMetadata(has_more=False, limit=25).total is None

    with pytest.raises(ValidationError):
        OffsetPagination(limit=101)
    with pytest.raises(ValidationError):
        CursorPagination(limit=0)


def test_sorting_requires_an_allowlisted_field() -> None:
    descending = parse_sort("-created_at", allowed_fields={"created_at", "name"})

    assert descending.field == "created_at"
    assert descending.direction is SortDirection.DESCENDING
    with pytest.raises(ValueError, match="Unsupported sort field"):
        parse_sort("private_field", allowed_fields={"name"})


def test_repeated_filter_values_are_preserved() -> None:
    filters = FilterParameters.from_mapping({"size": ["M", "L"]})

    assert filters.values == {"size": ("M", "L")}
