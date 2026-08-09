# Phase 5.11 — Retailer Catalog & Inventory Ingestion Foundation

## Status

Implemented. This phase adds a Store-scoped orchestration boundary for turning
retailer spreadsheets and image packages into the existing canonical catalog.
It does not introduce a second product, media, pricing, or inventory model.

## Boundary and lifecycle

An import moves through `created → validating → validated → processing →
completed`. Validation errors produce `validation_failed`; canonical commit
errors produce `failed`. Temporary PostgreSQL records retain job metadata,
normalized rows, structured errors, and staged media metadata for inspection and
audit. They are not marketplace entities.

The initial source types are `pos`, `manual`, `platform_staff`, and
`spreadsheet`. They all enter the same normalized pipeline. A future POS or API
adapter should implement source-to-normalized-row translation and must then use
this validation and canonical commit path.

## Spreadsheet contract

CSV and XLSX files are supported. Files are limited to 5 MiB and 10,000 rows;
expanded XLSX data is limited to 50 MiB. Macros are not loaded and formulas or
formula-like cells are rejected. CSV must be UTF-8.

Required columns are:

- `product_sku`, `product_name`, `category`, `variant_sku`
- `price`, `currency`, `quantity_on_hand`

Optional columns are `operation`, `description`, `brand`, `collection`, `size`,
`color`, `attributes`, `image_references`, and `metadata`. `operation` is
`auto`, `create`, or `update`. Additional attributes use semicolon-separated
`key=value` pairs. Image filenames use `|` as the separator. Metadata is a JSON
object. Prices use canonical currency validation and at most four decimal
places; inventory is a non-negative integer.

Validation reports row number, field, stable error code, message, and severity.
It checks required values, types, duplicate Variant SKUs, consistent Product
rows, normalized attribute values, Store-local taxonomy, canonical SKU
conflicts, prices, quantities, and staged images. Preview never mutates canonical
tables.

## Image package

Clients first create an import, then upload referenced images and a spreadsheet.
References are safe basenames such as `sku-001-front.jpg`; paths and traversal
segments are rejected. JPEG, PNG, WebP, and AVIF are accepted after content,
size, dimension, and pixel-count validation. Staged images use the existing
object-storage provider and storage transaction. Filename and SHA-256 duplicates
are rejected. On commit, media is created through `ProductMediaService` and can
be associated deterministically with the Product and Variant.

## Preview, commit, and idempotency

`POST /api/v1/catalog-imports/{id}/validate` enriches rows with the canonical
identifiers and optimistic versions observed during preview. It labels each row
`create`, `update`, `skip`, `conflict`, or `error`.

`POST /api/v1/catalog-imports/{id}/commit` accepts only a validated job. It uses
existing Product, Product Variant, Taxonomy, Pricing, Product Media, and Inventory
services inside the request-owned transaction. A stale canonical version fails
the job and rolls back all canonical changes. Retrying a completed commit is
idempotent.

Job creation requires an `Idempotency-Key`; the same key and request return the
same job, while reuse for another request conflicts. Duplicate spreadsheet
checksums are rejected per Store. Canonical matching uses Store + Product SKU and
Store + Variant reference. Ambiguous matches are reported and never overwritten.

## Canonical ownership and inventory rules

- Products and Variants remain owned by the Product bounded context.
- Categories and Collections remain owned by Catalog Taxonomy.
- Images remain owned by Product Media and stored through the existing provider.
- Prices remain owned by Pricing and Price Lists.
- Inventory remains the authoritative Inventory snapshot plus movement ledger.

New inventory is created through `InventoryService`. Existing stock is changed
through physical reconciliation, not a blind overwrite. Reconciliation locks the
Inventory row, checks its previewed version, preserves reserved quantity, rejects
a physical count below protected Reservations, appends a movement with source
`catalog_import`, and emits the normal Inventory outbox events. The established
Inventory-before-Reservation lock order is unchanged.

## Authorization and API

All endpoints require the existing bearer authentication and `catalog:view` or
`catalog:update` permissions. Store scope uses the shared access predicate:
Store owners and active accepted Store staff may operate the Store; outsiders see
`404` concealment.

- `POST /api/v1/catalog-imports`
- `POST /api/v1/catalog-imports/{id}/spreadsheet`
- `POST /api/v1/catalog-imports/{id}/media`
- `POST /api/v1/catalog-imports/{id}/validate`
- `POST /api/v1/catalog-imports/{id}/commit`
- `GET /api/v1/catalog-imports`
- `GET /api/v1/catalog-imports/{id}`
- `GET /api/v1/catalog-imports/{id}/rows`
- `GET /api/v1/catalog-imports/{id}/errors`

OpenAPI declares authentication and the common `401`, `403`, concealed `404`,
and lifecycle/idempotency `409` responses.

## Events and operations

Identifier-only `catalog_import.created`, `catalog_import.validated`,
`catalog_import.completed`, and `catalog_import.failed` events use the Phase 5.9
transactional outbox. Payloads contain identifiers and lifecycle metadata, never
spreadsheet rows, names, prices, image URLs, or customer data.

Low-cardinality metrics cover imports created, validated, completed and failed;
rows processed and rejected; duration; and image validation failures. No Store,
SKU, actor, or filename is a metric label.

