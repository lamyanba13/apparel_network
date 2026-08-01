from collections.abc import AsyncIterator
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import DatabaseSessionManager
from app.modules.catalogs.api.taxonomy_schemas import (
    CategoryCreateRequest,
    CategoryUpdateRequest,
    CollectionCreateRequest,
    CollectionUpdateRequest,
    ReorderRequest,
)
from app.modules.catalogs.application.taxonomy_services import (
    CategoryService,
    CollectionService,
)
from app.modules.catalogs.infrastructure.taxonomy_repositories import (
    SqlAlchemyTaxonomyRepository,
)
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity

router = APIRouter(tags=["Catalog Taxonomy"])


async def taxonomy_session(request: Request) -> AsyncIterator[AsyncSession]:
    manager = cast(DatabaseSessionManager, request.app.state.database)
    async with manager.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def services(
    request: Request, session: Annotated[AsyncSession, Depends(taxonomy_session)]
) -> tuple[CategoryService, CollectionService]:
    repository = SqlAlchemyTaxonomyRepository(session)
    events = request.app.state.store_events
    return CategoryService(repository, events), CollectionService(repository, events)


def _category(value: Any) -> dict[str, Any]:
    return {
        "id": value.id,
        "store_id": value.store_id,
        "name": value.name,
        "slug": value.slug,
        "description": value.description,
        "parent_category_id": value.parent_category_id,
        "sort_order": value.sort_order,
        "status": value.status,
        "visibility": value.visibility,
        "version": value.version,
    }


def _collection(value: Any) -> dict[str, Any]:
    return {
        "id": value.id,
        "store_id": value.store_id,
        "name": value.name,
        "slug": value.slug,
        "description": value.description,
        "sort_order": value.sort_order,
        "status": value.status,
        "visibility": value.visibility,
        "collection_type": value.collection_type,
        "version": value.version,
    }


@router.post(
    "/categories",
    dependencies=[require_permission("catalog:update")],
    status_code=201,
)
async def create_category(
    payload: CategoryCreateRequest,
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> dict[str, Any]:
    service = CategoryService(
        SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
    )
    value = await service.create(payload.model_dump(), identity.user.id)
    return _category(value)


@router.get("/categories", dependencies=[require_permission("catalog:view")])
async def list_categories(
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> list[dict[str, Any]]:
    return [
        _category(value)
        for value in await CategoryService(
            SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
        ).list(identity.user.id)
    ]


@router.get(
    "/categories/{entity_id}", dependencies=[require_permission("catalog:view")]
)
async def get_category(
    entity_id: UUID,
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> dict[str, Any]:
    return _category(
        await CategoryService(
            SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
        ).get(entity_id, identity.user.id)
    )


@router.patch(
    "/categories/{entity_id}",
    dependencies=[require_permission("catalog:update")],
)
async def update_category(
    entity_id: UUID,
    payload: CategoryUpdateRequest,
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> dict[str, Any]:
    return _category(
        await CategoryService(
            SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
        ).update(
            entity_id,
            identity.user.id,
            payload.model_dump(exclude={"version"}, exclude_unset=True),
            payload.version,
        )
    )


@router.delete(
    "/categories/{entity_id}",
    status_code=204,
    dependencies=[require_permission("catalog:update")],
)
async def delete_category(
    entity_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> Response:
    await CategoryService(
        SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
    ).delete(entity_id, identity.user.id, version)
    return Response(status_code=204)


@router.post(
    "/categories/{entity_id}/products/{product_id}",
    status_code=204,
    dependencies=[require_permission("catalog:update")],
)
async def assign_category(
    entity_id: UUID,
    product_id: UUID,
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> Response:
    await CategoryService(
        SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
    ).assign(entity_id, product_id, identity.user.id)
    return Response(status_code=204)


@router.delete(
    "/categories/{entity_id}/products/{product_id}",
    status_code=204,
    dependencies=[require_permission("catalog:update")],
)
async def remove_category(
    entity_id: UUID,
    product_id: UUID,
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> Response:
    await CategoryService(
        SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
    ).remove(entity_id, product_id, identity.user.id)
    return Response(status_code=204)


@router.post(
    "/collections",
    dependencies=[require_permission("catalog:update")],
    status_code=201,
)
async def create_collection(
    payload: CollectionCreateRequest,
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> dict[str, Any]:
    value = await CollectionService(
        SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
    ).create(payload.model_dump(), identity.user.id)
    return _collection(value)


@router.get("/collections", dependencies=[require_permission("catalog:view")])
async def list_collections(
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> list[dict[str, Any]]:
    return [
        _collection(value)
        for value in await CollectionService(
            SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
        ).list(identity.user.id)
    ]


@router.get(
    "/collections/{entity_id}", dependencies=[require_permission("catalog:view")]
)
async def get_collection(
    entity_id: UUID,
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> dict[str, Any]:
    return _collection(
        await CollectionService(
            SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
        ).get(entity_id, identity.user.id)
    )


@router.patch(
    "/collections/{entity_id}",
    dependencies=[require_permission("catalog:update")],
)
async def update_collection(
    entity_id: UUID,
    payload: CollectionUpdateRequest,
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> dict[str, Any]:
    return _collection(
        await CollectionService(
            SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
        ).update(
            entity_id,
            identity.user.id,
            payload.model_dump(exclude={"version"}, exclude_unset=True),
            payload.version,
        )
    )


@router.delete(
    "/collections/{entity_id}",
    status_code=204,
    dependencies=[require_permission("catalog:update")],
)
async def delete_collection(
    entity_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> Response:
    await CollectionService(
        SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
    ).delete(entity_id, identity.user.id, version)
    return Response(status_code=204)


@router.post(
    "/collections/{entity_id}/products/{product_id}",
    status_code=204,
    dependencies=[require_permission("catalog:update")],
)
async def assign_collection(
    entity_id: UUID,
    product_id: UUID,
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> Response:
    await CollectionService(
        SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
    ).assign(entity_id, product_id, identity.user.id)
    return Response(status_code=204)


@router.delete(
    "/collections/{entity_id}/products/{product_id}",
    status_code=204,
    dependencies=[require_permission("catalog:update")],
)
async def remove_collection(
    entity_id: UUID,
    product_id: UUID,
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> Response:
    await CollectionService(
        SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
    ).remove(entity_id, product_id, identity.user.id)
    return Response(status_code=204)


@router.post(
    "/collections/{entity_id}/reorder",
    dependencies=[require_permission("catalog:update")],
)
async def reorder_collection(
    entity_id: UUID,
    payload: ReorderRequest,
    identity: CurrentIdentity,
    request: Request,
    session: Annotated[AsyncSession, Depends(taxonomy_session)],
) -> dict[str, Any]:
    return _collection(
        await CollectionService(
            SqlAlchemyTaxonomyRepository(session), request.app.state.store_events
        ).reorder(
            entity_id,
            identity.user.id,
            payload.product_ids,
            payload.version,
        )
    )
