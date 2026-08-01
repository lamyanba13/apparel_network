from uuid import uuid4

import pytest

from app.common.exceptions import AppError
from app.modules.catalogs.application.taxonomy_services import (
    HierarchyService,
    TaxonomyValidationService,
)


def test_slug_normalization_is_deterministic() -> None:
    assert (
        TaxonomyValidationService.slug("  Summer / New  Arrivals ")
        == "summer-new-arrivals"
    )


def test_reserved_slug_is_rejected() -> None:
    with pytest.raises(AppError):
        TaxonomyValidationService.slug("admin")


def test_invalid_sort_order_is_rejected_by_schema() -> None:
    from app.modules.catalogs.api.taxonomy_schemas import CategoryCreateRequest

    with pytest.raises(ValueError):
        CategoryCreateRequest(store_id=uuid4(), name="x", slug="x", sort_order=-1)


@pytest.mark.asyncio
async def test_hierarchy_rejects_cycle() -> None:
    category_id, parent_id, store_id = uuid4(), uuid4(), uuid4()

    class Repository:
        async def category_in_store(self, category: object, store: object) -> bool:
            return True

        async def parent_id(self, category: object) -> object:
            return category_id

    with pytest.raises(AppError):
        await HierarchyService(Repository()).validate_parent(
            category_id, parent_id, store_id
        )
