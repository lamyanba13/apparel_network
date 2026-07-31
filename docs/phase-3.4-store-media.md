# Phase 3.4 Store Media

## Scope

Phase 3.4 adds Store-only image media inside the Store bounded context. It
supports Store logos, banners, and gallery images backed by the approved
S3-compatible storage abstraction and the existing private
`fashion-network-media` bucket.

This phase does not add a generic Uploads API, product/catalog media, inventory
images, avatars, brand media, CDN delivery, image transformation, thumbnails,
compression, background jobs, AI processing, OCR, video, audio, PDF,
notifications, analytics, search, frontend, or dashboard behavior.

Identity, Store profile, Store Verification, and Store Membership remain
backward compatible. Store Media consumes only the frozen authenticated
principal, permission checks, and owner-scoped Store repository behavior.

## Architecture

```text
Store Media API
    -> StoreMediaService
        -> StoreMediaValidationService
        -> StoreMediaRepository
        -> StorageProvider
        -> StoreMediaStorageTransaction
        -> StoreMediaAuditService
            -> PostgreSQL metadata transaction
            -> MinIO locally / Cloudflare R2 in production
```

PostgreSQL is authoritative for media ownership, lifecycle, ordering, and
visibility metadata. Object storage contains binary bytes only. Redis and
RabbitMQ are not used by Store Media.

Repositories flush but never commit. The Store Media request dependency owns
the database commit and object-storage compensation:

- a new object is uploaded before metadata flush and is deleted if the database
  transaction rolls back;
- deletion first moves the object to a private tombstone key;
- database metadata is soft-deleted;
- rollback moves the tombstone back to its original key;
- successful database commit permanently deletes the tombstone.

This avoids exposing a deleted object after metadata rollback and avoids
retaining a newly uploaded object after a failed database request. A storage
failure after a successful database commit can leave only a private tombstone,
never publicly usable metadata.

## Database schema

Alembic revision `2eb2bce458d5` creates `store_media` after Phase 3.3 head
`47f0ff7d40b8`.

| Column                         | Rule                                                       |
| ------------------------------ | ---------------------------------------------------------- |
| `id`                           | Application-generated UUIDv7 primary key                   |
| `store_id`                     | Required Store reference, restrictive deletion             |
| `uploaded_by`                  | Required Identity user reference, restrictive deletion     |
| `media_type`                   | `logo`, `banner`, or `gallery`                             |
| `status`                       | `active`, `archived`, or `deleted`                         |
| `original_filename`            | Sanitized display metadata only                            |
| `stored_filename`              | UUID-generated filename                                    |
| `extension`                    | Canonical validated extension                              |
| `mime_type`                    | MIME determined from decoded content                       |
| `file_size`                    | Positive validated byte count                              |
| `width`, `height`              | Positive decoded dimensions                                |
| `orientation`                  | EXIF orientation from `1` through `8`                      |
| `aspect_ratio`                 | Positive six-decimal width/height ratio                    |
| `checksum_sha256`              | Lowercase SHA-256 digest                                   |
| `bucket`, `object_key`, `etag` | Private object-storage identity                            |
| `display_order`                | Non-negative presentation order                            |
| `is_public`                    | Visibility intent; does not make the private bucket public |
| `created_at`, `updated_at`     | Timezone-aware server timestamps                           |
| `deleted_at`                   | Required only for soft-deleted metadata                    |
| `version`                      | Positive optimistic version                                |

Database constraints enforce positive size, dimensions, ratio and version,
valid orientation and checksum, non-negative ordering, lifecycle-consistent
soft deletion, and globally unique object keys.

Partial unique indexes enforce:

- one active logo per Store;
- one active banner per Store;
- no duplicate non-deleted checksum per Store.

Lookup indexes cover Store, type, display order, status, uploader, active
Store/type ordering, and non-deleted Store reads.

## Object key layout

Original filenames never form storage keys:

```text
stores/{store_id}/logos/{uuid}.ext
stores/{store_id}/banners/{uuid}.ext
stores/{store_id}/gallery/{uuid}.ext
```

The bucket remains private. Presigned URLs are generated on demand, expire
after 15 minutes by default, and are never stored in PostgreSQL or included in
events.

## Storage provider

The `StorageProvider` application port exposes:

- upload;
- download;
- delete;
- copy;
- move;
- exists;
- stat;
- list;
- presigned upload generation;
- presigned download generation.

`MinIOStorageProvider` implements only the tested S3-compatible subset. It uses
MinIO in development and can target Cloudflare R2 through configuration. The
provider contains transport translation only; Store ownership, validation,
replacement, ordering, and lifecycle behavior remain in application services.

## Image validation

Accepted MIME types are exactly:

- `image/jpeg`;
- `image/png`;
- `image/webp`;
- `image/avif`.

GIF, SVG, BMP, TIFF, HEIC, PDF, archives, executables, unknown formats, empty
files, and malformed images are rejected.

Validation independently checks:

- sanitized basename and extension;
- declared Content-Type;
- magic-byte signature;
- Pillow-decoded image format and content;
- positive dimensions and a 40-megapixel decompression boundary;
- type-specific byte limits;
- computed SHA-256;
- optional client checksum using constant-time comparison.

Limits are 5 MiB for logos, 10 MiB for banners, and 15 MiB for gallery images.
The API reads at most one byte beyond the applicable limit before rejecting the
upload.

## Business rules

- Uploading a logo archives the prior active logo before inserting the new
  active record in the same PostgreSQL transaction.
- Uploading a banner follows the same singleton replacement rule.
- Gallery images are unlimited.
- Duplicate non-deleted bytes within one Store are rejected.
- Gallery reordering requires unique media IDs, unique non-negative positions,
  gallery-only records, and an optimistic version for every item.
- Metadata updates can change only display order and visibility.
- Deletion is always metadata soft deletion plus compensated object removal.
- Cross-Store and non-owner access returns `404`.
- No Store Media operation compares Identity role names.

## API

| Method and path                                     | Permission     | Result                       |
| --------------------------------------------------- | -------------- | ---------------------------- |
| `POST /api/v1/stores/{store_id}/media/logo`         | `store:update` | Upload or replace logo       |
| `POST /api/v1/stores/{store_id}/media/banner`       | `store:update` | Upload or replace banner     |
| `POST /api/v1/stores/{store_id}/media/gallery`      | `store:update` | Upload gallery image         |
| `GET /api/v1/stores/{store_id}/media`               | `store:view`   | List non-deleted Store media |
| `GET /api/v1/stores/{store_id}/media/{media_id}`    | `store:view`   | Read one Store image         |
| `PATCH /api/v1/stores/{store_id}/media/{media_id}`  | `store:update` | Update safe metadata         |
| `DELETE /api/v1/stores/{store_id}/media/{media_id}` | `store:delete` | Soft-delete one image        |
| `POST /api/v1/stores/{store_id}/media/reorder`      | `store:update` | Reorder gallery images       |

Upload routes use multipart bodies for the image and safe scalar metadata.
Responses expose a newly generated presigned download URL and its expiry, but
never the bucket, object key, checksum, ETag, or stored filename. Errors use the
platform RFC 9457 representation.

The provider supports presigned PUT operations for a future reviewed
intent/finalization flow. Phase 3.4 does not add unapproved upload-intent or
finalization routes and never persists a presigned URL.

## Events

The safe typed events are:

- `StoreLogoUploaded`;
- `StoreBannerUploaded`;
- `StoreGalleryUploaded`;
- `StoreMediaDeleted`;
- `StoreMediaReordered`.

Payloads contain only event ID, timestamp, optional correlation ID, Store ID,
media ID, media type, and schema version. They exclude bytes, filenames, URLs,
presigned URLs, checksums, ETags, buckets, and object keys.

## Metrics

The low-cardinality Prometheus counters are:

- `fashion_network_store_media_upload_total`;
- `fashion_network_store_media_delete_total`;
- `fashion_network_store_media_bytes_total`;
- `fashion_network_store_media_failures_total`.

They have no Store, user, media, filename, MIME, key, or checksum labels.

## Dependencies

Phase 3.4 adds only:

- `minio` for the approved S3-compatible provider;
- `Pillow` for decoded-image validation and trusted metadata extraction;
- `python-multipart` for bounded FastAPI multipart parsing.

No background-job, transformation, CDN, machine-learning, OCR, video, or
generic upload framework dependency is added.

## Phase boundary

Phase 3.5 may build the next approved Store capability. It must not turn Store
Media into product media, introduce public CDN behavior, add media workers, or
weaken ownership, validation, transaction compensation, event privacy, or
private-bucket guarantees without a separately reviewed phase.
