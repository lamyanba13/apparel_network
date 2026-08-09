from __future__ import annotations

from io import BytesIO
from typing import cast
from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient
from openpyxl import Workbook
from PIL import Image
from prometheus_client import generate_latest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalogs.application.taxonomy_services import CategoryService
from app.modules.catalogs.domain import Catalog
from app.modules.catalogs.infrastructure.taxonomy_models import ProductCategoryModel
from app.modules.catalogs.infrastructure.taxonomy_repositories import (
    SqlAlchemyTaxonomyRepository,
)
from app.modules.identity.application.services import AuthenticatedIdentity
from app.modules.ingestion.application.parsers import SpreadsheetParser
from app.modules.ingestion.infrastructure.models import CatalogImportModel
from app.modules.inventory.domain import InventoryMovementType
from app.modules.inventory.infrastructure.models import (
    InventoryItemModel,
    InventoryMovementModel,
)
from app.modules.pricing.infrastructure.models import ProductPriceModel
from app.modules.products.domain import Product, ProductVariant
from app.modules.products.infrastructure.attribute_models import EventOutboxModel
from app.modules.products.infrastructure.media_models import ProductMediaModel
from app.modules.products.infrastructure.models import ProductModel
from app.modules.products.infrastructure.variant_models import ProductVariantModel
from app.modules.stores.application.membership_schemas import (
    StoreMembershipInvitation,
)
from app.modules.stores.domain import Store, StoreMembershipRole
from tests.test_inventory import _authorized_client
from tests.test_order import _authorized_client as _role_client
from tests.test_order import _second_identity
from tests.test_store_membership import _service as _membership_service

pytest_plugins = (
    "tests.fixtures.database",
    "tests.fixtures.application",
    "tests.fixtures.identity",
    "tests.fixtures.stores",
    "tests.fixtures.catalogs",
    "tests.fixtures.products",
)

_HEADER = (
    "operation,product_sku,product_name,description,brand,category,collection,"
    "variant_sku,size,color,attributes,price,currency,quantity_on_hand,"
    "image_references,metadata\n"
)


def _csv(
    *,
    operation: str = "auto",
    product_sku: str = "IMPORT-PRODUCT-001",
    product_name: str = "Imported Linen Shirt",
    variant_sku: str = "IMPORT-VARIANT-001",
    category: str = "Shirts",
    price: str = "1499.0000",
    quantity: int = 7,
    image: str = "front.png|back.png",
) -> bytes:
    return (
        _HEADER
        + operation
        + ","
        + product_sku
        + ","
        + product_name
        + ",Breathable linen shirt,Local Brand,"
        + category
        + ",,"
        + variant_sku
        + ",Medium,Black,,"
        + price
        + ",INR,"
        + str(quantity)
        + ","
        + image
        + ",{}\n"
    ).encode()


def _png(color: tuple[int, int, int] = (20, 40, 80)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), color=color).save(output, format="PNG")
    return output.getvalue()


def _metric(name: str) -> float:
    prefix = f"{name} "
    return next(
        float(line.removeprefix(prefix))
        for line in generate_latest().decode().splitlines()
        if line.startswith(prefix)
    )


async def _category(
    session: AsyncSession,
    application: FastAPI,
    store: Store,
) -> None:
    await CategoryService(
        SqlAlchemyTaxonomyRepository(session), application.state.store_events
    ).create(
        {
            "store_id": store.id,
            "name": "Shirts",
            "slug": "shirts",
            "status": "active",
            "visibility": "public",
        },
        store.owner_id,
    )


async def _create_import(
    client: AsyncClient,
    headers: dict[str, str],
    store: Store,
    catalog: Catalog,
    *,
    key: str,
    source: str = "spreadsheet",
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/catalog-imports",
        headers={**headers, "Idempotency-Key": key},
        json={
            "store_id": str(store.id),
            "catalog_id": str(catalog.id),
            "source_type": source,
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


async def test_catalog_import_preview_commit_update_media_inventory_and_outbox(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    catalog: Catalog,
    product_variant: ProductVariant,
    db_session: AsyncSession,
    application: FastAPI,
) -> None:
    del product_variant  # creates the canonical Size/Color attribute values
    created_before = _metric("fashion_network_catalog_imports_created_total")
    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        await _category(db_session, application, verified_store)
        created = await _create_import(
            client,
            headers,
            verified_store,
            catalog,
            key="catalog-import-create-0001",
            source="platform_staff",
        )
        repeated = await _create_import(
            client,
            headers,
            verified_store,
            catalog,
            key="catalog-import-create-0001",
            source="platform_staff",
        )
        assert repeated["id"] == created["id"]
        import_id = created["id"]

        media = await client.post(
            f"/api/v1/catalog-imports/{import_id}/media",
            headers=headers,
            files={"file": ("front.png", _png(), "image/png")},
        )
        assert media.status_code == 201, media.text
        assert media.json()["width"] == 32
        second_media = await client.post(
            f"/api/v1/catalog-imports/{import_id}/media",
            headers=headers,
            files={"file": ("back.png", _png((80, 40, 20)), "image/png")},
        )
        assert second_media.status_code == 201, second_media.text
        duplicate_media = await client.post(
            f"/api/v1/catalog-imports/{import_id}/media",
            headers=headers,
            files={"file": ("front.png", _png(), "image/png")},
        )
        assert duplicate_media.status_code == 409

        upload = await client.post(
            f"/api/v1/catalog-imports/{import_id}/spreadsheet",
            headers=headers,
            files={"file": ("catalog.csv", _csv(), "text/csv")},
        )
        assert upload.status_code == 200, upload.text
        assert upload.json()["status"] == "created"
        assert (
            await db_session.scalar(
                select(ProductModel.id).where(ProductModel.sku == "IMPORT-PRODUCT-001")
            )
            is None
        )

        preview = await client.post(
            f"/api/v1/catalog-imports/{import_id}/validate", headers=headers
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["catalog_import"]["status"] == "validated"
        assert preview.json()["valid_rows"] == 1
        rows = await client.get(
            f"/api/v1/catalog-imports/{import_id}/rows", headers=headers
        )
        assert rows.status_code == 200
        assert rows.json()["items"][0]["action"] == "create"

        committed = await client.post(
            f"/api/v1/catalog-imports/{import_id}/commit", headers=headers
        )
        assert committed.status_code == 200, committed.text
        assert committed.json()["status"] == "completed"
        repeated_commit = await client.post(
            f"/api/v1/catalog-imports/{import_id}/commit", headers=headers
        )
        assert repeated_commit.status_code == 200
        assert repeated_commit.json()["id"] == import_id

        update_job = await _create_import(
            client,
            headers,
            verified_store,
            catalog,
            key="catalog-import-update-0002",
            source="pos",
        )
        update_id = update_job["id"]
        update_upload = await client.post(
            f"/api/v1/catalog-imports/{update_id}/spreadsheet",
            headers=headers,
            files={
                "file": (
                    "catalog-update.csv",
                    _csv(
                        product_name="Updated Linen Shirt",
                        price="1599.0000",
                        quantity=5,
                        image="",
                    ),
                    "text/csv",
                )
            },
        )
        assert update_upload.status_code == 200, update_upload.text
        update_preview = await client.post(
            f"/api/v1/catalog-imports/{update_id}/validate", headers=headers
        )
        assert update_preview.status_code == 200, update_preview.text
        update_rows = await client.get(
            f"/api/v1/catalog-imports/{update_id}/rows", headers=headers
        )
        assert update_rows.json()["items"][0]["action"] == "update"
        update_commit = await client.post(
            f"/api/v1/catalog-imports/{update_id}/commit", headers=headers
        )
        assert update_commit.status_code == 200, update_commit.text
        assert update_commit.json()["status"] == "completed"

    product = await db_session.scalar(
        select(ProductModel).where(ProductModel.sku == "IMPORT-PRODUCT-001")
    )
    assert product is not None
    assert product.name == "Updated Linen Shirt"
    assert product.store_id == verified_store.id
    assert product.created_by_id == authenticated_identity.user.id
    variant = await db_session.scalar(
        select(ProductVariantModel).where(
            ProductVariantModel.reference == "IMPORT-VARIANT-001"
        )
    )
    assert variant is not None
    price = await db_session.scalar(
        select(ProductPriceModel).where(ProductPriceModel.variant_id == variant.id)
    )
    inventory = await db_session.scalar(
        select(InventoryItemModel).where(InventoryItemModel.variant_id == variant.id)
    )
    media = await db_session.scalar(
        select(ProductMediaModel).where(ProductMediaModel.product_id == product.id)
    )
    assert price is not None and str(price.base_price) == "1599.0000"
    assert inventory is not None and inventory.quantity_on_hand == 5
    assert inventory.quantity_reserved == 0
    assert media is not None and media.variant_id == variant.id
    assert (
        len(
            (
                await db_session.scalars(
                    select(ProductMediaModel).where(
                        ProductMediaModel.product_id == product.id
                    )
                )
            ).all()
        )
        == 2
    )
    assert (
        await db_session.scalar(
            select(ProductCategoryModel.product_id).where(
                ProductCategoryModel.product_id == product.id
            )
        )
        == product.id
    )
    movement = await db_session.scalar(
        select(InventoryMovementModel).where(
            InventoryMovementModel.inventory_id == inventory.id,
            InventoryMovementModel.movement_type
            == InventoryMovementType.RECONCILIATION,
        )
    )
    assert movement is not None
    assert movement.source == "catalog_import"
    assert str(movement.reference_id) == update_id
    event_names = set(
        await db_session.scalars(
            select(EventOutboxModel.event_name).where(
                EventOutboxModel.event_name.like("catalog_import.%")
            )
        )
    )
    assert {
        "catalog_import.created",
        "catalog_import.validated",
        "catalog_import.completed",
    } <= event_names
    assert _metric("fashion_network_catalog_imports_created_total") >= (
        created_before + 2
    )


async def test_catalog_import_structured_errors_duplicate_and_access_control(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    catalog: Catalog,
    product_variant: ProductVariant,
    db_session: AsyncSession,
) -> None:
    del product_variant
    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        unauthorized = await client.get("/api/v1/catalog-imports")
        assert unauthorized.status_code == 401
        hidden = await client.post(
            "/api/v1/catalog-imports",
            headers={**headers, "Idempotency-Key": "catalog-import-hidden-0001"},
            json={
                "store_id": str(uuid4()),
                "catalog_id": str(uuid4()),
                "source_type": "spreadsheet",
            },
        )
        assert hidden.status_code == 404

        created = await _create_import(
            client,
            headers,
            verified_store,
            catalog,
            key="catalog-import-invalid-0001",
        )
        upload = await client.post(
            f"/api/v1/catalog-imports/{created['id']}/spreadsheet",
            headers=headers,
            files={
                "file": (
                    "invalid.csv",
                    _csv(category="Unknown", image="missing.png"),
                    "text/csv",
                )
            },
        )
        assert upload.status_code == 200
        preview = await client.post(
            f"/api/v1/catalog-imports/{created['id']}/validate", headers=headers
        )
        assert preview.status_code == 200
        assert preview.json()["catalog_import"]["status"] == "validation_failed"
        errors = await client.get(
            f"/api/v1/catalog-imports/{created['id']}/errors", headers=headers
        )
        assert errors.status_code == 200
        codes = {item["code"] for item in errors.json()["items"]}
        assert {"unknown_category", "missing_image"} <= codes
        assert (
            await db_session.scalar(
                select(ProductModel.id).where(ProductModel.sku == "IMPORT-PRODUCT-001")
            )
            is None
        )

        duplicate = await _create_import(
            client,
            headers,
            verified_store,
            catalog,
            key="catalog-import-invalid-0002",
        )
        duplicate_upload = await client.post(
            f"/api/v1/catalog-imports/{duplicate['id']}/spreadsheet",
            headers=headers,
            files={
                "file": (
                    "duplicate.csv",
                    _csv(category="Unknown", image="missing.png"),
                    "text/csv",
                )
            },
        )
        assert duplicate_upload.status_code == 409
    failed = await db_session.get(CatalogImportModel, created["id"])
    assert failed is not None and failed.error_count == 2


async def test_stale_inventory_rolls_back_canonical_import_transaction(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    catalog: Catalog,
    product: Product,
    product_variant: ProductVariant,
    db_session: AsyncSession,
    application: FastAPI,
) -> None:
    await _category(db_session, application, verified_store)
    original_name = product.name
    async with _authorized_client(async_client, authenticated_identity, db_session) as (
        client,
        headers,
    ):
        inventory_response = await client.post(
            "/api/v1/inventory",
            headers=headers,
            json={
                "variant_id": str(product_variant.id),
                "quantity_on_hand": 12,
                "quantity_reserved": 3,
                "status": "active",
                "tracking_policy": "track",
                "low_stock_threshold": 2,
            },
        )
        assert inventory_response.status_code == 201, inventory_response.text
        inventory_payload = inventory_response.json()
        created = await _create_import(
            client,
            headers,
            verified_store,
            catalog,
            key="catalog-import-stale-0001",
        )
        upload = await client.post(
            f"/api/v1/catalog-imports/{created['id']}/spreadsheet",
            headers=headers,
            files={
                "file": (
                    "stale.csv",
                    _csv(
                        operation="update",
                        product_sku=product.sku,
                        product_name="Name that must roll back",
                        variant_sku=product_variant.reference,
                        price="899.0000",
                        quantity=8,
                        image="",
                    ),
                    "text/csv",
                )
            },
        )
        assert upload.status_code == 200, upload.text
        preview = await client.post(
            f"/api/v1/catalog-imports/{created['id']}/validate", headers=headers
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["catalog_import"]["status"] == "validated"

        concurrent_reconciliation = await client.post(
            f"/api/v1/inventory/{inventory_payload['id']}/reconcile",
            headers=headers,
            json={
                "physical_count": 11,
                "reason": "Concurrent physical count",
                "version": inventory_payload["version"],
                "source": "physical_count",
            },
        )
        assert concurrent_reconciliation.status_code == 200
        assert concurrent_reconciliation.json()["quantity_reserved"] == 3
        commit = await client.post(
            f"/api/v1/catalog-imports/{created['id']}/commit", headers=headers
        )
        assert commit.status_code == 200, commit.text
        assert commit.json()["status"] == "failed"
        errors = await client.get(
            f"/api/v1/catalog-imports/{created['id']}/errors", headers=headers
        )
        assert {item["code"] for item in errors.json()["items"]} == {
            "canonical_commit_failed"
        }

    db_session.expire_all()
    persisted_product = await db_session.get(ProductModel, product.id)
    persisted_inventory = await db_session.get(
        InventoryItemModel, inventory_payload["id"]
    )
    assert persisted_product is not None and persisted_product.name == original_name
    assert persisted_inventory is not None
    assert persisted_inventory.quantity_on_hand == 11
    assert persisted_inventory.quantity_reserved == 3
    assert (
        await db_session.scalar(
            select(ProductPriceModel.id).where(
                ProductPriceModel.variant_id == product_variant.id
            )
        )
        is None
    )
    assert (
        await db_session.scalar(
            select(InventoryMovementModel.id).where(
                InventoryMovementModel.inventory_id == persisted_inventory.id,
                InventoryMovementModel.source == "catalog_import",
            )
        )
        is None
    )


def test_spreadsheet_parser_supports_xlsx_and_rejects_formulas() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(
        [
            "product_sku",
            "product_name",
            "category",
            "variant_sku",
            "size",
            "color",
            "price",
            "currency",
            "quantity_on_hand",
        ]
    )
    sheet.append(
        [
            "XLSX-PRODUCT",
            "XLSX Shirt",
            "Shirts",
            "XLSX-VARIANT",
            "Medium",
            "Black",
            "=100+20",
            "INR",
            4,
        ]
    )
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    parsed = SpreadsheetParser().parse(
        "catalog.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        output.getvalue(),
    )
    assert parsed.rows == []
    assert {error.code for error in parsed.errors} == {"formula_not_allowed"}
    mixed = SpreadsheetParser().parse(
        "mixed.csv",
        "text/csv",
        _csv(image="")
        + b"auto,BAD,Invalid,,,,,BAD-VARIANT,Medium,Black,,oops,USD,-1,,{}\n",
    )
    assert len(mixed.rows) == 1
    assert {error.code for error in mixed.errors} >= {
        "invalid_price",
        "invalid_quantity",
    }


async def test_accepted_store_staff_can_commit_import_and_openapi_is_documented(
    async_client: AsyncClient,
    authenticated_identity: AuthenticatedIdentity,
    verified_store: Store,
    catalog: Catalog,
    product_variant: ProductVariant,
    db_session: AsyncSession,
    application: FastAPI,
) -> None:
    del product_variant
    await _category(db_session, application, verified_store)
    staff = await _second_identity(db_session)
    memberships = _membership_service(db_session, application.state.store_events)
    invitation = await memberships.invite(
        verified_store.id,
        authenticated_identity.user.id,
        StoreMembershipInvitation(staff.user.id, StoreMembershipRole.STAFF),
    )
    await memberships.accept(
        verified_store.id,
        invitation.id,
        staff.user.id,
        invitation.version,
    )
    async with _role_client(
        async_client,
        staff,
        db_session,
        role="store_staff",
    ) as (client, headers):
        created = await _create_import(
            client,
            headers,
            verified_store,
            catalog,
            key="catalog-import-staff-0001",
            source="platform_staff",
        )
        upload = await client.post(
            f"/api/v1/catalog-imports/{created['id']}/spreadsheet",
            headers=headers,
            files={"file": ("staff.csv", _csv(image=""), "text/csv")},
        )
        assert upload.status_code == 200, upload.text
        preview = await client.post(
            f"/api/v1/catalog-imports/{created['id']}/validate", headers=headers
        )
        assert preview.status_code == 200, preview.text
        committed = await client.post(
            f"/api/v1/catalog-imports/{created['id']}/commit", headers=headers
        )
        assert committed.status_code == 200, committed.text
        assert committed.json()["status"] == "completed"

    product = await db_session.scalar(
        select(ProductModel).where(ProductModel.sku == "IMPORT-PRODUCT-001")
    )
    assert product is not None and product.created_by_id == staff.user.id
    operation = application.openapi()["paths"]["/api/v1/catalog-imports"]["post"]
    assert operation["security"]
    assert {"201", "401", "403", "404", "409"} <= set(operation["responses"])
