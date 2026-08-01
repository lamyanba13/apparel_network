# Phase 4.3 — Product Media

Product media is an isolated Product/Catalog capability backed by the existing
StorageProvider and MinIO-compatible implementation. PostgreSQL stores metadata;
objects are addressed only by server-generated keys under
`products/{product_id}/{role}/{uuid}.ext`.

Supported content types are JPEG, PNG, WebP, AVIF, and MP4. Product ownership
is checked through the existing Store ownership boundary and unauthorized or
cross-store access is returned as not found. Repositories flush only; the HTTP
dependency owns database and compensating storage transaction commit/rollback.

The API exposes primary, gallery, video, list, detail, and deletion routes under
`/api/v1/products/{product_id}/media`. Presigned URLs are generated on demand
and are never persisted. Media events contain identifiers and metadata only,
never filenames, URLs, MIME types, or user data.

The migration creates `product_media` with ownership foreign keys, soft-delete
and optimistic-version constraints, active-primary uniqueness, checksum
deduplication, and product/store/catalog/order indexes.
