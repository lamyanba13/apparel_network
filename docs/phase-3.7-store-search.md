# Phase 3.7 — Store Search and Discovery

Status: implemented, pending review and release tagging  
Date: 2026-08-01

## Scope

This phase adds public Store discovery without changing the Store system of
record. PostgreSQL remains authoritative. Meilisearch stores a rebuildable
projection and is updated asynchronously by Celery through RabbitMQ. No Store
CRUD, Identity, authorization, analytics, media, or operating-hours behavior
was changed.

## Public index contract

The `stores` index contains only:

`store_id`, `name`, `slug`, `description`, `category`, `city`, `state`,
`country`, `postal_code`, `latitude`, `longitude`, `verified`, `active`,
`currently_open`, `logo_exists`, `banner_exists`, `media_count`, `created_at`,
`updated_at`.

Coordinates are also emitted as Meilisearch `_geo` metadata when present so
native geo filtering and nearest sorting can be used. No owner IDs, contacts,
membership data, verification notes, audit fields, or deleted records are
projected.

Searchable attributes are name, description, category, city, state, and
country. Filterable attributes are verified, active, category, city, state,
country, and currently_open. Sortable attributes are created_at, updated_at,
name, and `_geo`; `store_id` is the distinct attribute.

## Architecture

- `StoreSearchService` normalizes query text, validates filters and geo
  parameters, applies pagination/sort policy, and returns public DTOs.
- `MeilisearchStoreRepository` is the provider adapter. It owns index
  configuration, search, autocomplete, document writes, deletes, and bounded
  bulk rebuilds.
- `StoreSearchProjectionBuilder` reads Store, media, and operating-hours data
  from PostgreSQL and creates the public document.
- `stores.search.sync` and `stores.search.rebuild` are Celery tasks routed to
  the durable `store-search` RabbitMQ queue. The queue has a dead-letter
  exchange and queue for failed messages.

## Synchronization

Store lifecycle, verification, media, and hours events are mapped to
`StoreSearchSyncRequested` with `index`, `update`, or `delete` operations.
The HTTP transaction only emits the request; it never calls Meilisearch. The
worker is idempotent: an ineligible or deleted store is removed, while an
eligible store is indexed or updated. Provider failures are retried with
bounded exponential backoff and counted. Rebuild reads authoritative IDs,
reprojects eligible stores in chunks, and emits a rebuild event.

`StoreClosed` maps to a search delete because closed stores are not public.
There is no separate StoreDeleted event in the frozen Store lifecycle API.

## API

- `GET /api/v1/stores/search` is public and supports query, city, state,
  country, category, verified, currently_open, latitude, longitude, radius,
  limit, offset, and relevance/alphabetical/newest/recently_updated/nearest
  sorting.
- `GET /api/v1/stores/search/autocomplete` is public and returns only
  `store_id`, `name`, and `slug`.
- `POST /api/v1/stores/search/rebuild` is restricted to `system:manage` and
  queues an asynchronous rebuild.

Nearest sorting and radius filtering require latitude and longitude together;
distance is calculated by Meilisearch native geo support, never in Python.

## Events and metrics

Search events contain only `store_id`, operation (where applicable), and
timestamp: `StoreIndexed`, `StoreUpdatedInSearch`, `StoreRemovedFromSearch`,
and `StoreSearchRebuilt`.

Metrics are low-cardinality counters:

- `fashion_network_store_search_queries_total`
- `fashion_network_store_search_results_total`
- `fashion_network_store_search_index_updates_total`
- `fashion_network_store_search_failures_total`

## Recovery and operations

The index can be recreated and rebuilt from PostgreSQL at any time. A
Meilisearch outage does not affect Store writes; RabbitMQ backlog is retried
after recovery. Search provider errors return a bounded service-unavailable
response, while public documents remain protected by the verified/active
projection policy.

No database migration is required for this phase.
