from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol
from uuid import UUID

from app.modules.stores.domain.search import (
    StoreAutocompleteItem,
    StoreSearchDocument,
    StoreSearchPage,
)


class StoreSearchRepository(Protocol):
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
    ) -> StoreSearchPage: ...

    async def autocomplete(
        self,
        *,
        query: str,
        limit: int,
    ) -> Sequence[StoreAutocompleteItem]: ...

    async def index_store(self, document: StoreSearchDocument) -> None: ...

    async def update_store(self, document: StoreSearchDocument) -> None: ...

    async def delete_store(self, store_id: UUID) -> None: ...

    async def bulk_rebuild(self, documents: Sequence[StoreSearchDocument]) -> None: ...

    async def configure_index(self) -> None: ...
