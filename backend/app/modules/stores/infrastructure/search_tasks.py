from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from celery import Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.modules.stores.domain.search_events import (
    StoreIndexed,
    StoreRemovedFromSearch,
    StoreSearchRebuilt,
    StoreUpdatedInSearch,
)
from app.modules.stores.infrastructure.events import StoreEventPublisher
from app.modules.stores.infrastructure.persistence.models import StoreModel
from app.modules.stores.infrastructure.search_projection import build_store_document
from app.modules.stores.infrastructure.search_repository import (
    MeilisearchStoreRepository,
    SearchProviderError,
)
from app.observability.metrics import (
    STORE_SEARCH_FAILURES,
    STORE_SEARCH_INDEX_UPDATES,
)
from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="stores.search.sync",
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def sync_store_search(self: Task, store_id: str, operation: str) -> str:
    try:
        asyncio.run(_sync_store(UUID(store_id), operation))
    except SearchProviderError as error:
        STORE_SEARCH_FAILURES.inc()
        retry = self.retry
        raise retry(exc=error, countdown=2 ** min(_retry_count(self), 5)) from error
    return store_id


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="stores.search.rebuild",
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
def rebuild_store_search(self: Task) -> int:
    try:
        return asyncio.run(_rebuild())
    except SearchProviderError as error:
        STORE_SEARCH_FAILURES.inc()
        retry = self.retry
        raise retry(exc=error, countdown=2 ** min(_retry_count(self), 5)) from error


async def _sync_store(store_id: UUID, operation: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            repository = MeilisearchStoreRepository(settings)
            await repository.configure_index()
            document = await build_store_document(session, store_id)
            if operation == "delete" or document is None:
                await repository.delete_store(store_id)
                await StoreEventPublisher().publish(
                    StoreRemovedFromSearch(store_id=store_id, operation="delete")
                )
                STORE_SEARCH_INDEX_UPDATES.inc()
            else:
                await repository.update_store(document)
                event_type = (
                    StoreIndexed if operation == "index" else StoreUpdatedInSearch
                )
                await StoreEventPublisher().publish(
                    event_type(store_id=store_id, operation=operation)
                )
                STORE_SEARCH_INDEX_UPDATES.inc()
    finally:
        await engine.dispose()


async def _rebuild() -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            repository = MeilisearchStoreRepository(settings)
            await repository.configure_index()
            store_ids = await session.scalars(
                select(StoreModel.id).where(StoreModel.deleted_at.is_(None))
            )
            from app.modules.stores.domain.search import StoreSearchDocument

            documents: list[StoreSearchDocument] = []
            for store_id in store_ids:
                document = await build_store_document(session, store_id)
                if document is not None:
                    documents.append(document)
            await repository.bulk_rebuild(documents)
            STORE_SEARCH_INDEX_UPDATES.inc()
            await StoreEventPublisher().publish(
                StoreSearchRebuilt(store_id=UUID(int=0), operation="rebuild")
            )
            return len(documents)
    finally:
        await engine.dispose()


def _retry_count(task: Task) -> int:
    request = getattr(task, "request", None)
    return int(getattr(request, "retries", 0))
