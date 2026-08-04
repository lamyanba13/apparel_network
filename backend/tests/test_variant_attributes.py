from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from prometheus_client import generate_latest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.events import EventPublisher
from app.database.session import get_db
from app.modules.identity.application.authorization import (
    PermissionCache,
    PermissionService,
)
from app.modules.identity.application.services import (
    AuthenticatedIdentity,
    TokenService,
)
from app.modules.identity.domain.authorization import PermissionRegistry
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyIdentityGrantRepository,
    SqlAlchemyPermissionRepository,
    SqlAlchemyRoleRepository,
)
from app.modules.products.api.attribute_schemas import (
    AttributeResponse,
    AttributeValueResponse,
    VariantAttributeAssignmentResponse,
    VariantAttributeValueResponse,
)
from app.modules.products.api.schemas import ProductVariantResponse
from app.modules.products.domain import (
    AttributeStatus,
    OutboxStatus,
    Product,
    ProductVariant,
)
from app.modules.products.infrastructure.attribute_models import (
    EventOutboxModel,
    ProductAttributeModel,
    ProductAttributeValueModel,
    ProductVariantAttributeValueModel,
)
from app.modules.stores.domain import Store

pytest_plugins = (
    "tests.fixtures.database",
    "tests.fixtures.application",
    "tests.fixtures.identity",
    "tests.fixtures.stores",
    "tests.fixtures.catalogs",
    "tests.fixtures.products",
)


def _counter_value(name: str) -> float:
    prefix = f"{name} "
    return next(
        float(line.removeprefix(prefix))
        for line in generate_latest().decode().splitlines()
        if line.startswith(prefix)
    )


@asynccontextmanager
async def _authorized_client(
    async_client: AsyncClient,
    identity: AuthenticatedIdentity,
    db_session: AsyncSession,
) -> AsyncIterator[tuple[AsyncClient, dict[str, str]]]:
    transport = cast(ASGITransport, async_client._transport)
    application = cast(FastAPI, transport.app)
    permissions = PermissionService(
        db_session,
        SqlAlchemyRoleRepository(db_session),
        SqlAlchemyPermissionRepository(db_session),
        SqlAlchemyIdentityGrantRepository(db_session),
        cast(PermissionCache, application.state.permission_cache),
        PermissionRegistry(),
        cast(EventPublisher, application.state.authentication_events),
    )
    await permissions.assign_role(
        identity.user.id, "store_owner", assigned_by_id=identity.user.id
    )
    connection = await db_session.connection()
    request_session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async def request_database() -> AsyncIterator[AsyncSession]:
        yield request_session

    application.dependency_overrides[get_db] = request_database
    token = cast(TokenService, application.state.token_service).create_access_token(
        user_id=identity.user.id, session_id=identity.session.id
    )
    try:
        yield async_client, {"Authorization": f"Bearer {token}"}
    finally:
        application.dependency_overrides.pop(get_db, None)
        await request_session.close()


async def test_attribute_crud_assignment_normalization_outbox_and_metrics(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    attributes_before = _counter_value("fashion_network_attribute_created_total")
    values_before = _counter_value("fashion_network_attribute_value_created_total")
    assignments_before = _counter_value(
        "fashion_network_variant_attribute_assigned_total"
    )
    outbox_before = _counter_value("fashion_network_outbox_written_total")
    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        initial = await client.get(
            f"/api/v1/variants/{product_variant.id}/attributes", headers=headers
        )
        created_response = await client.post(
            "/api/v1/attributes",
            headers=headers,
            json={
                "store_id": str(verified_store.id),
                "name": "Material",
                "slug": "material",
                "type": "enum",
                "required": False,
                "filterable": True,
                "searchable": True,
                "sort_order": 2,
            },
        )
        assert created_response.status_code == 201, created_response.text
        attribute = AttributeResponse.model_validate(created_response.json())
        duplicate = await client.post(
            "/api/v1/attributes",
            headers=headers,
            json={
                "store_id": str(verified_store.id),
                "name": "Duplicate Material",
                "slug": "material",
                "type": "text",
            },
        )
        wrong_store = await client.post(
            "/api/v1/attributes",
            headers=headers,
            json={
                "store_id": str(UUID(int=99)),
                "name": "Wrong",
                "slug": "wrong",
                "type": "text",
            },
        )
        value_response = await client.post(
            f"/api/v1/attributes/{attribute.id}/values",
            headers=headers,
            json={"value": "Linen", "slug": "linen", "sort_order": 0},
        )
        assert value_response.status_code == 201, value_response.text
        value = AttributeValueResponse.model_validate(value_response.json())
        duplicate_value = await client.post(
            f"/api/v1/attributes/{attribute.id}/values",
            headers=headers,
            json={"value": "Other Linen", "slug": "linen"},
        )
        updated_response = await client.patch(
            f"/api/v1/attributes/{attribute.id}",
            headers=headers,
            json={"description": "Natural fabric", "version": attribute.version},
        )
        updated = AttributeResponse.model_validate(updated_response.json())
        stale_update = await client.patch(
            f"/api/v1/attributes/{attribute.id}",
            headers=headers,
            json={"name": "Stale", "version": attribute.version},
        )
        assignment_response = await client.post(
            f"/api/v1/variants/{product_variant.id}/attributes",
            headers=headers,
            json={
                "attribute_value_id": str(value.id),
                "version": product_variant.version,
            },
        )
        assert assignment_response.status_code == 201, assignment_response.text
        assignment = VariantAttributeAssignmentResponse.model_validate(
            assignment_response.json()
        )
        duplicate_assignment = await client.post(
            f"/api/v1/variants/{product_variant.id}/attributes",
            headers=headers,
            json={"attribute_value_id": str(value.id), "version": 2},
        )
        listed = await client.get(
            f"/api/v1/variants/{product_variant.id}/attributes", headers=headers
        )
        removed = await client.delete(
            f"/api/v1/variants/{product_variant.id}/attributes/{value.id}",
            headers=headers,
            params={"version": 2},
        )
        value_deleted = await client.delete(
            f"/api/v1/attribute-values/{value.id}",
            headers=headers,
            params={"version": value.version},
        )
        stale_delete = await client.delete(
            f"/api/v1/attributes/{attribute.id}",
            headers=headers,
            params={"version": attribute.version},
        )
        deleted = await client.delete(
            f"/api/v1/attributes/{attribute.id}",
            headers=headers,
            params={"version": updated.version},
        )

    assert initial.status_code == 200
    initial_values = [
        VariantAttributeValueResponse.model_validate(item) for item in initial.json()
    ]
    assert [item.attribute_slug for item in initial_values] == ["color", "size"]
    assert attribute.id.version == 7 and attribute.status is AttributeStatus.ACTIVE
    assert duplicate.status_code == 409
    assert wrong_store.status_code == 404
    assert duplicate_value.status_code == 409
    assert updated.version == 2
    assert stale_update.status_code == 409
    assert assignment.variant_id == product_variant.id
    assert assignment.attribute_value_id == value.id
    assert duplicate_assignment.status_code == 409
    listed_values = [
        VariantAttributeValueResponse.model_validate(item) for item in listed.json()
    ]
    assert [item.attribute_slug for item in listed_values] == [
        "color",
        "size",
        "material",
    ]
    assert removed.status_code == 204
    assert value_deleted.status_code == 204
    assert stale_delete.status_code == 409
    assert deleted.status_code == 204

    attribute_model = await db_session.get(ProductAttributeModel, attribute.id)
    assert attribute_model is not None
    assert attribute_model.status is AttributeStatus.ARCHIVED
    assert attribute_model.deleted_at is not None
    assert attribute_model.deleted_by_id == authenticated_identity.user.id
    assert await db_session.get(ProductAttributeValueModel, value.id) is None
    assert (
        await db_session.get(ProductVariantAttributeValueModel, assignment.id) is None
    )
    outbox = (
        await db_session.scalars(
            select(EventOutboxModel)
            .where(EventOutboxModel.aggregate_id == product_variant.id)
            .order_by(EventOutboxModel.occurred_at, EventOutboxModel.id)
        )
    ).all()
    assert {item.event_name for item in outbox} >= {
        "product_variant.created",
        "product_variant.attribute_assigned",
        "product_variant.attribute_removed",
    }
    assert all(item.status is OutboxStatus.PENDING for item in outbox)
    assert all(item.published_at is None and item.retry_count == 0 for item in outbox)
    for item in outbox:
        assert set(item.payload) == {
            "aggregate_id",
            "store_id",
            "product_id",
            "variant_id",
            "version",
            "timestamp",
        }
    assert _counter_value("fashion_network_attribute_created_total") == (
        attributes_before + 1
    )
    assert _counter_value("fashion_network_attribute_value_created_total") == (
        values_before + 1
    )
    assert _counter_value("fashion_network_variant_attribute_assigned_total") == (
        assignments_before + 1
    )
    assert _counter_value("fashion_network_outbox_written_total") == outbox_before + 2


async def test_variant_mutations_write_transactional_outbox(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        archived_response = await client.patch(
            f"/api/v1/products/{product.id}/variants/{product_variant.id}",
            headers=headers,
            json={"is_active": False, "version": product_variant.version},
        )
        archived = ProductVariantResponse.model_validate(archived_response.json())
        stale_delete = await client.delete(
            f"/api/v1/products/{product.id}/variants/{product_variant.id}",
            headers=headers,
            params={"version": product_variant.version},
        )
        deleted = await client.delete(
            f"/api/v1/products/{product.id}/variants/{product_variant.id}",
            headers=headers,
            params={"version": archived.version},
        )

    assert archived_response.status_code == 200
    assert not archived.is_active and archived.version == 2
    assert stale_delete.status_code == 409
    assert deleted.status_code == 204
    names = set(
        await db_session.scalars(
            select(EventOutboxModel.event_name).where(
                EventOutboxModel.aggregate_id == product_variant.id
            )
        )
    )
    assert {
        "product_variant.created",
        "product_variant.updated",
        "product_variant.archived",
        "product_variant.deleted",
    } <= names


def test_attribute_openapi_documents_routes_and_permissions(
    application: FastAPI,
) -> None:
    schema = application.openapi()
    expected = {
        ("post", "/api/v1/attributes", "attribute:create"),
        ("get", "/api/v1/attributes", "attribute:view"),
        ("patch", "/api/v1/attributes/{attribute_id}", "attribute:update"),
        ("delete", "/api/v1/attributes/{attribute_id}", "attribute:update"),
        (
            "post",
            "/api/v1/attributes/{attribute_id}/values",
            "attribute:update",
        ),
        ("patch", "/api/v1/attribute-values/{value_id}", "attribute:update"),
        ("delete", "/api/v1/attribute-values/{value_id}", "attribute:update"),
        ("post", "/api/v1/variants/{variant_id}/attributes", "attribute:assign"),
        ("get", "/api/v1/variants/{variant_id}/attributes", "attribute:view"),
        (
            "delete",
            "/api/v1/variants/{variant_id}/attributes/{value_id}",
            "attribute:assign",
        ),
    }
    for method, path, permission in expected:
        operation = schema["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-authorization"] == [
            {"kind": "permission", "values": [permission]}
        ]
