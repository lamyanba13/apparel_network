from collections.abc import Collection, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.common.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.common.enums import SortDirection


class OffsetPagination(BaseModel):
    """Bounded offset pagination for approved small, stable collections."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class CursorPagination(BaseModel):
    """Opaque cursor pagination, the default for mutable collections."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cursor: str | None = Field(default=None, min_length=1, max_length=2048)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class PageMetadata(BaseModel):
    """Provider-neutral metadata returned with a bounded collection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    next_cursor: str | None = None
    has_more: bool
    limit: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total: int | None = Field(default=None, ge=0)
    offset: int | None = Field(default=None, ge=0)


class SortParameter(BaseModel):
    """One allowlisted sort field and its direction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    direction: SortDirection


class FilterParameters(BaseModel):
    """Normalized repeated filter values without business-field interpretation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    values: Mapping[str, tuple[str, ...]] = Field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Sequence[str]],
    ) -> "FilterParameters":
        return cls(values={key: tuple(items) for key, items in values.items()})


def parse_sort(
    value: str,
    *,
    allowed_fields: Collection[str],
) -> SortParameter:
    """Parse API `sort=field` or `sort=-field` syntax against an allowlist."""
    direction = (
        SortDirection.DESCENDING if value.startswith("-") else SortDirection.ASCENDING
    )
    field = value.removeprefix("-")
    if field not in allowed_fields:
        raise ValueError(f"Unsupported sort field: {field}")
    return SortParameter(field=field, direction=direction)
